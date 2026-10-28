"""Build a source release with no runtime invoices, raw corpus, caches or secrets."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0,str(ROOT/'src'))
from invoice_intelligence import __version__

def main():
    target=ROOT/f'dist/invoice-intelligence-{__version__}.zip';target.parent.mkdir(exist_ok=True)
    files=[]
    for name in ['src','scripts','tests','docs','examples','frontend','output/pdf','deploy']:
        folder=ROOT/name
        if folder.exists():files += [p for p in folder.rglob('*') if p.is_file() and not any(part in {'__pycache__','node_modules','dist','.output','.vercel','.tanstack','.git'} for part in p.parts) and not p.name.endswith(('.pyc','.pyo')) and not any(part.endswith('.egg-info') for part in p.parts)]
    files += [ROOT/name for name in ['README.md','pyproject.toml','requirements.lock.txt','.env.example','.gitignore','Dockerfile','Dockerfile.vercel','vercel.json','.dockerignore'] if (ROOT/name).exists()]
    manifest={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(files))}
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        for relative in manifest:archive.write(ROOT/relative,'invoice-intelligence/'+relative)
        archive.writestr('invoice-intelligence/RELEASE_MANIFEST.json',json.dumps(manifest,indent=2)+'\n')
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        assert not any('/data/' in n or '/.venv/' in n or '/reports/' in n or '/web_data/' in n or '/.secrets/' in n or n.endswith('/.env') for n in archive.namelist())
    (target.parent/f'invoice-intelligence-{__version__}.sha256').write_text(hashlib.sha256(target.read_bytes()).hexdigest()+'  '+target.name+'\n')
    print(target, len(manifest),'files')

if __name__=='__main__':main()
