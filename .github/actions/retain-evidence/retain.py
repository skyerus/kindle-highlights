"""Retain selected non-secret job evidence for the Mac's host-side collector."""
import glob,hashlib,json,os,pathlib,re,tarfile

def main():
    root=pathlib.Path(os.environ['LOCAL_ACTIONS_EVIDENCE_DIR'])
    if str(root)!='/opt/actions/evidence' and os.environ.get('EVIDENCE_TESTING')!='1':
        raise SystemExit('Unexpected local evidence destination')
    name=os.environ['EVIDENCE_NAME']
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,180}',name):raise SystemExit('Invalid artifact name')
    allowed=[pathlib.Path(os.environ[k]).resolve() for k in ['GITHUB_WORKSPACE','RUNNER_TEMP']]
    selected={}
    for pattern in os.environ['EVIDENCE_PATHS'].splitlines():
        pattern=pattern.strip()
        if not pattern:continue
        for match in glob.glob(pattern,recursive=True):
            path=pathlib.Path(match)
            for p in (path.rglob('*') if path.is_dir() else [path]):
                if not p.is_file():continue
                if p.is_symlink() or any(parent.is_symlink() for parent in p.absolute().parents):raise SystemExit('Symlink evidence is not accepted')
                resolved=p.resolve()
                prefix=next((base for base in allowed if resolved.is_relative_to(base)),None)
                if prefix is None:raise SystemExit('Evidence must be inside the workspace or runner temp')
                relative=resolved.relative_to(prefix)
                if any(part.startswith('.') for part in relative.parts):continue
                selected[str(resolved)]=(resolved,relative.as_posix())
    if not selected:
        policy=os.environ.get('EVIDENCE_MISSING','warn')
        if policy=='error':raise SystemExit('No evidence files found')
        if policy=='warn':print('::warning::No evidence files found')
        return
    if sum(p.stat().st_size for p,_ in selected.values())>512*1024*1024:raise SystemExit('Evidence exceeds the 512 MiB artifact limit')
    root.mkdir(parents=True,exist_ok=True)
    dest=root/(name+'.tar.gz')
    if dest.exists():raise SystemExit('Evidence name already exists')
    files=[]
    with tarfile.open(dest,'w:gz') as archive:
        for index,(p,relative) in enumerate(sorted(selected.values())):
            arcname=f'{index}/{relative}'
            archive.add(p,arcname=arcname,recursive=False)
            files.append({'archive_path':arcname,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    digest=hashlib.sha256(dest.read_bytes()).hexdigest()
    manifest={'name':name,'repository':os.environ.get('GITHUB_REPOSITORY'),'run_id':os.environ.get('GITHUB_RUN_ID'),'run_attempt':os.environ.get('GITHUB_RUN_ATTEMPT'),'source_sha':os.environ.get('GITHUB_SHA'),'retention_days':int(os.environ.get('EVIDENCE_RETENTION','14')),'archive_sha256':digest,'files':files}
    (root/(name+'.json')).write_text(json.dumps(manifest,indent=2)+'\n')
    print(f'Retained {len(files)} evidence files locally: {name}; SHA-256 {digest}')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as summary:
            summary.write(f'\nEvidence **{name}** is retained on the MacBook in `~/.local/share/github-actions-mac/evidence/`. SHA-256: `{digest}`.\n')
if __name__=='__main__':main()
