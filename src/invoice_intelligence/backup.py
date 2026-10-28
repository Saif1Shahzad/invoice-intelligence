"""Verified offline backup and restore. Stop API and worker before invoking."""
import argparse,hashlib,json,os,shutil,sqlite3
from pathlib import Path
from datetime import datetime,timezone

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def outside(source,dest):
    if dest==source or source in dest.parents or dest in source.parents:raise ValueError('Backup and runtime must be separate, non-nested directories.')
def backup(source,dest):
    source=source.resolve();dest=dest.resolve();outside(source,dest)
    if dest.exists():raise ValueError('Destination already exists; backups are never overwritten.')
    db=source/'documents.sqlite3'
    if not db.is_file():raise ValueError('No invoice database at source.')
    dest.mkdir(parents=True,mode=0o700)
    # Caller must stop both processes; database backup still handles WAL correctly.
    with sqlite3.connect(db) as connection,sqlite3.connect(dest/db.name) as target:
        connection.backup(target)
        if target.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('Database integrity check failed.')
    for path in source.rglob('*'):
        if path.name in {'documents.sqlite3','documents.sqlite3-wal','documents.sqlite3-shm'}:continue
        if path.is_symlink():raise ValueError('Symlinks are not supported in runtime backups.')
        target=dest/path.relative_to(source)
        if path.is_dir():target.mkdir(exist_ok=True,mode=0o700)
        elif path.is_file():target.parent.mkdir(parents=True,exist_ok=True,mode=0o700);shutil.copyfile(path,target);target.chmod(0o600)
    (dest/db.name).chmod(0o600)
    manifest={'created_at':datetime.now(timezone.utc).isoformat(),'files':{str(p.relative_to(dest)):sha(p) for p in dest.rglob('*') if p.is_file()},'notice':'Sensitive invoice data. Store on encrypted storage. API and worker must be stopped during backup.'}
    (dest/'BACKUP.json').write_text(json.dumps(manifest,indent=2));(dest/'BACKUP.json').chmod(0o600)
    return manifest

def restore(source,dest):
    source=source.resolve();dest=dest.resolve();outside(source,dest)
    if dest.exists():raise ValueError('Restore destination must be new; existing runtimes are never overwritten.')
    manifest=json.loads((source/'BACKUP.json').read_text())
    for name,digest in manifest['files'].items():
        relative=Path(name)
        if relative.is_absolute() or '..' in relative.parts or (source/relative).is_symlink():raise ValueError('Unsafe backup path.')
        if sha(source/relative)!=digest:raise ValueError('Backup content differs from its manifest.')
    with sqlite3.connect(f'file:{source / "documents.sqlite3"}?mode=ro',uri=True) as c:
        if c.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('Backup database is corrupt.')
    dest.mkdir(parents=True,mode=0o700)
    for name in manifest['files']:
        target=dest/name;target.parent.mkdir(parents=True,exist_ok=True,mode=0o700);shutil.copyfile(source/name,target);target.chmod(0o600)
    return len(manifest['files'])
def main():
    p=argparse.ArgumentParser(description='Offline verified invoice backup/restore');p.add_argument('operation',choices=['backup','restore']);p.add_argument('source',type=Path);p.add_argument('destination',type=Path);p.add_argument('--offline',action='store_true',help='Confirm both API and worker have been stopped');a=p.parse_args()
    if not a.offline:p.error('Stop API and worker, then pass --offline.')
    try:result=backup(a.source,a.destination) if a.operation=='backup' else restore(a.source,a.destination)
    except (ValueError,OSError,sqlite3.Error) as e:p.exit(1,f'Backup operation failed: {e}\n')
    print('Verified',a.operation,'completed:',a.destination)
if __name__=='__main__':main()
