"""Create local hashed accounts without putting passwords in shell history."""
import argparse,getpass,json,os,secrets
from pathlib import Path
from invoice_intelligence.security import password_hash

def main():
    p=argparse.ArgumentParser(description='Add or rotate a pilot account');p.add_argument('username');p.add_argument('--role',choices=['viewer','reviewer','admin'],default='reviewer');p.add_argument('--file',type=Path,default=Path('.secrets/accounts.json'));a=p.parse_args()
    if not a.username.strip() or ':' in a.username or len(a.username)>80:p.error('Use a nonempty username without a colon, at most 80 characters.')
    password=getpass.getpass('Password (at least 14 characters): ')
    if len(password)<14 or password!=getpass.getpass('Repeat password: '):p.error('Passwords must match and contain at least 14 characters.')
    a.file.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    data=json.loads(a.file.read_text()) if a.file.exists() else {};salt=secrets.token_hex(16)
    data[a.username]={'role':a.role,'salt':salt,'hash':password_hash(password,salt)}
    temp=a.file.with_suffix('.tmp');fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:json.dump(data,f,indent=2)
    temp.replace(a.file);print('Account saved. Restart the API to load changed accounts.')
if __name__=='__main__':main()
