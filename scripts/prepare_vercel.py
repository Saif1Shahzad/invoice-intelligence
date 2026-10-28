"""Prepare a Vercel routing project for an existing HTTPS invoice backend."""
import argparse,json
from pathlib import Path
from urllib.parse import urlsplit

def prepare(origin,output):
    u=urlsplit(origin)
    if u.scheme!='https' or not u.hostname or u.username or u.password or u.query or u.fragment or u.path not in ('','/'):
        raise ValueError('Use an HTTPS backend origin only, without credentials, path or query.')
    if u.hostname in {'localhost','127.0.0.1','0.0.0.0'}:raise ValueError('Vercel needs a reachable HTTPS backend, not a local address.')
    output.mkdir(parents=True,exist_ok=True)
    public=output/'public';public.mkdir(exist_ok=True)
    (public/'index.html').write_text('<!doctype html><title>Invoice review</title><p>The invoice backend is unavailable. Check the configured API origin.</p>')
    config={'$schema':'https://openapi.vercel.sh/vercel.json','framework':None,'outputDirectory':'public',
      'rewrites':[{'source':'/:path*','destination':origin.rstrip('/')+'/:path*'}],
      'headers':[{'source':'/:path*','headers':[{'key':'Cache-Control','value':'private, no-store'},{'key':'Referrer-Policy','value':'no-referrer'}]}]}
    (output/'vercel.json').write_text(json.dumps(config,indent=2)+'\n')
    return config

def main():
    p=argparse.ArgumentParser();p.add_argument('--api-origin',required=True);p.add_argument('--output',type=Path,default=Path('deploy/vercel'));a=p.parse_args()
    try:prepare(a.api_origin,a.output)
    except ValueError as e:p.error(str(e))
    print('Vercel project prepared:',a.output,'— no API key or invoice data included.')
if __name__=='__main__':main()
