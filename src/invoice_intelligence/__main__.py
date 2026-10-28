"""Start the local API and its worker together. Ctrl+C stops only owned children."""
import argparse
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time


def main():
    parser=argparse.ArgumentParser(description='Invoice Intelligence local release')
    sub=parser.add_subparsers(dest='command',required=True)
    serve=sub.add_parser('serve',help='Run the API and worker with one shared configuration')
    serve.add_argument('--port',type=int,default=8000)
    serve.add_argument('--data-dir',type=Path,help='Optional dedicated data folder')
    args=parser.parse_args()
    if not 1<=args.port<=65535: parser.error('Port must be between 1 and 65535.')
    from invoice_intelligence.environment import load_environment
    load_environment()
    env=os.environ.copy()
    if args.data_dir: env['INVOICE_DATA_DIR']=str(args.data_dir.resolve())
    if env.get('INVOICE_DATA_DIR'): env['INVOICE_DATA_DIR']=str(Path(env['INVOICE_DATA_DIR']).resolve())
    try:
        with socket.socket() as check: check.bind(('127.0.0.1',args.port))
    except OSError:
        parser.exit(1,f'Port {args.port} is unavailable. Stop the existing server with Ctrl+C or choose --port.\n')
    children=[]
    def stop(*_): raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,stop)
    try:
        api=subprocess.Popen([sys.executable,'-m','uvicorn','invoice_intelligence.api.main:app','--host','127.0.0.1','--port',str(args.port)],env=env,start_new_session=True)
        children.append(api)
        time.sleep(.6)
        if api.poll() is not None: return api.returncode or 1
        worker=subprocess.Popen([sys.executable,'-m','invoice_intelligence.workers.runner'],env=env,start_new_session=True)
        children.append(worker)
        print(f'Invoice Intelligence: http://127.0.0.1:{args.port}/ · Ctrl+C stops API and worker.',flush=True)
        while all(p.poll() is None for p in children): time.sleep(.5)
        return next((p.returncode for p in children if p.returncode),1)
    except KeyboardInterrupt: return 0
    finally:
        for child in children:
            if child.poll() is None: child.send_signal(signal.SIGINT)
        for child in children:
            try: child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                child.terminate()
                try: child.wait(timeout=3)
                except subprocess.TimeoutExpired: child.kill();child.wait()

if __name__=='__main__':sys.exit(main())
