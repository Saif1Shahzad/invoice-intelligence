"""Small non-executing .env loader. Shell/environment values take precedence."""
import os
from pathlib import Path
import re

def load_environment(path=None):
    path=Path(path or os.environ.get('INVOICE_ENV_FILE','.env'))
    if not path.is_file():return
    if path.stat().st_size>65536:raise ValueError('Environment file is too large')
    for line in path.read_text().splitlines():
        line=line.strip()
        if not line or line.startswith('#'):continue
        if line.startswith('export '):line=line[7:]
        key,sep,value=line.partition('=');key=key.strip();value=value.strip()
        if not sep or not re.fullmatch(r'[A-Z][A-Z0-9_]*',key):raise ValueError('Invalid environment setting')
        if len(value)>=2 and value[0]==value[-1] and value[0] in ('"',"'"):value=value[1:-1]
        if key=="GROQ_API_KEY" and value in {"configure_locally","paste_your_groq_key_here"}:continue
        os.environ.setdefault(key,value)
