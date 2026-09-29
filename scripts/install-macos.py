#!/usr/bin/env python3
"""Install the local highlight collector as a per-user macOS LaunchAgent."""
import argparse
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

LABEL = 'com.skye.reading-highlights'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', default='skyerus/kindle-highlights')
    parser.add_argument('--branch', default='main')
    parser.add_argument('--port', type=int, default=8084)
    parser.add_argument('--app-dir', type=Path, default=Path.home() / 'Library/Application Support/Reading Highlights')
    parser.add_argument('--launch-agent-dir', type=Path, default=Path.home() / 'Library/LaunchAgents')
    parser.add_argument('--python', default=sys.executable)
    parser.add_argument('--no-start', action='store_true', help='Prepare files without loading the LaunchAgent.')
    args = parser.parse_args()
    if sys.platform != 'darwin':
        parser.error('This installer requires macOS.')
    if not 1024 <= args.port <= 65535:
        parser.error('Choose an unprivileged TCP port between 1024 and 65535.')
    source = Path(__file__).resolve().parents[1]
    runtime = Path(args.python).resolve()
    if not runtime.is_file() or not shutil.which('gh'):
        parser.error('Python and the authenticated GitHub CLI (gh) must be installed first.')
    # Confirm source exists before unloading an existing service.
    for name in ('collector.py', 'db.py'):
        if not (source / name).is_file():
            parser.error(f'Missing required source file: {name}')
    app = args.app_dir.expanduser().resolve()
    state, logs = app / 'data', app / 'logs'
    for directory in (app, state, logs, args.launch_agent_dir):
        directory.mkdir(parents=True, exist_ok=True)
    os.chmod(app, 0o700)
    os.chmod(state, 0o700)
    os.chmod(logs, 0o700)
    agent = args.launch_agent_dir / f'{LABEL}.plist'
    domain = f'gui/{os.getuid()}'
    if not args.no_start:
        subprocess.run(['launchctl', 'bootout', domain + '/' + LABEL], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for name in ('collector.py', 'db.py'):
        dest = app / name
        temp = dest.with_suffix('.tmp')
        shutil.copyfile(source / name, temp)
        os.chmod(temp, 0o600)
        os.replace(temp, dest)
    subprocess.run([str(runtime), str(app / 'collector.py'), 'init', '--state-dir', str(state)], check=True)
    gh_dir = str(Path(shutil.which('gh')).parent)
    spec = {
        'Label': LABEL,
        'ProgramArguments': [str(runtime), str(app / 'collector.py'), 'serve', '--state-dir', str(state),
                             '--host', '0.0.0.0', '--port', str(args.port), '--repo', args.repo,
                             '--branch', args.branch, '--publish-interval', '60'],
        'WorkingDirectory': str(app),
        'EnvironmentVariables': {'PATH': f'{gh_dir}:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin',
                                 'PYTHONUNBUFFERED': '1'},
        'RunAtLoad': True, 'KeepAlive': True, 'ThrottleInterval': 10, 'ProcessType': 'Background', 'Umask': 63,
        'StandardOutPath': str(logs / 'service.log'), 'StandardErrorPath': str(logs / 'service-error.log'),
    }
    temp_agent = agent.with_suffix('.tmp')
    temp_agent.write_bytes(plistlib.dumps(spec))
    os.chmod(temp_agent, 0o600)
    os.replace(temp_agent, agent)
    subprocess.run(['plutil', '-lint', str(agent)], check=True)
    if not args.no_start:
        subprocess.run(['launchctl', 'bootstrap', domain, str(agent)], check=True)
        subprocess.run(['launchctl', 'kickstart', domain + '/' + LABEL], check=True)
    print(f'Installed collector at {app}')
    print(f'LaunchAgent: {agent}')
    print(f'Local status: http://localhost:{args.port}/healthz')
    print('The device token is stored in data/token and is deliberately not printed.')
    print('Starts after login and restarts after crashes. An asleep or closed Mac may be unavailable; devices retain pending highlights.')


if __name__ == '__main__':
    main()
