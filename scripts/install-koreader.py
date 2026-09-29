#!/usr/bin/env python3
"""Install the shared-highlights plugin on a mounted KOReader device."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--koreader-dir', required=True, type=Path, help='For example /Volumes/Kindle/koreader; exit KOReader before USB mode.')
    parser.add_argument('--url', required=True, help='Mac collector base URL, such as http://192.168.0.221:8084')
    parser.add_argument('--token-file', type=Path, default=Path.home() / 'Library/Application Support/Reading Highlights/data/token')
    args = parser.parse_args()
    root = args.koreader_dir.resolve()
    if not (root / 'plugins').is_dir() or not (root / 'settings').is_dir():
        parser.error('Expected an existing KOReader installation with plugins and settings directories.')
    # Match the plugin trust boundary without accepting credentials or URL paths.
    from urllib.parse import urlsplit
    from ipaddress import ip_address
    parsed = urlsplit(args.url)
    host = parsed.hostname or ''
    try:
        address = ip_address(host)
        local = address.version == 4 and (address.is_loopback or any(address in __import__('ipaddress').ip_network(n) for n in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')))
    except ValueError:
        local = host == 'localhost' or host.endswith('.local')
    if parsed.scheme != 'http' or not local or parsed.username or parsed.password or parsed.path not in ('','/') or parsed.query or parsed.fragment:
        parser.error('Use a trusted LAN HTTP base URL without credentials, query or path.')
    try:
        port = parsed.port
    except ValueError:
        parser.error('Invalid collector port.')
    if port is not None and not 1 <= port <= 65535:
        parser.error('Invalid collector port.')
    token = args.token_file.read_text().strip()
    if len(token) < 32 or not token.isascii() or any(c.isspace() for c in token):
        parser.error('Collector token file is invalid.')
    source = Path(__file__).resolve().parents[1] / 'koreader/sharedhighlights.koplugin'
    if not (source / 'main.lua').is_file():
        parser.error('Plugin source is missing.')
    plugin = root / 'plugins/sharedhighlights.koplugin'
    config = root / 'settings/sharedhighlights-config.json'
    previous = json.loads(config.read_text()) if config.exists() else {}
    backup = root / 'shared-highlights-backups' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup.mkdir(parents=True)
    if plugin.exists():
        shutil.copytree(plugin, backup / plugin.name)
    if config.exists():
        shutil.copyfile(config, backup / config.name)
    queue = root / 'settings/sharedhighlights-queue.json'
    if queue.exists():
        shutil.copyfile(queue, backup / queue.name)
    staging = root / 'shared-highlights-install.tmp'
    if staging.exists():
        parser.error('A prior staging directory exists; inspect it before retrying.')
    shutil.copytree(source, staging, ignore=shutil.ignore_patterns('tests','__pycache__'))
    if plugin.exists():
        # The replacement is prepared and the previous copy backed up first.
        shutil.rmtree(plugin)
    staging.rename(plugin)
    contents = {'url': args.url.rstrip('/'), 'token': token,
                'device_id': previous.get('device_id') or 'koreader-' + uuid.uuid4().hex}
    temp = config.with_suffix('.tmp')
    with temp.open('w') as f:
        os.chmod(temp, 0o600)
        json.dump(contents, f)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    temp.replace(config)
    for p in source.glob('*.lua'):
        if p.read_bytes() != (plugin / p.name).read_bytes():
            raise RuntimeError('Plugin readback mismatch: ' + p.name)
    assert json.loads(config.read_text()) == contents
    print('Installed and paired shared highlights; plugin files and configuration verified.')
    print('Previous plugin/configuration, if any, backed up at:', backup)
    print('Safely eject the reader and restart KOReader. Highlights sync automatically when Wi-Fi and the collector are available.')
    print('For manual status: Tools > More tools > Shared highlights > Sync highlights.')
    print('The token was not printed.')


if __name__ == '__main__':
    main()
