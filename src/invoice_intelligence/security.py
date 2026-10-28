"""Single-team HTTP Basic authentication behind HTTPS, with server-bound audit identity."""
import base64,hashlib,hmac,json,time
from pathlib import Path
from collections import defaultdict,deque
from urllib.parse import urlsplit
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware


def password_hash(password,salt):return hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1,dklen=32).hex()

def load_accounts(path):
    if not path:return {}
    p=Path(path)
    if p.stat().st_size>65536:raise ValueError('Authentication file too large')
    accounts=json.loads(p.read_text())
    if not isinstance(accounts,dict) or not accounts or len(accounts)>50:raise ValueError('Invalid account configuration')
    for user,a in accounts.items():
        if not isinstance(user,str) or not user.strip() or len(user)>80 or ':' in user:raise ValueError('Invalid account name')
        if a.get('role') not in {'viewer','reviewer','admin'}:raise ValueError('Invalid account role')
        if len(bytes.fromhex(a['salt']))!=16 or len(bytes.fromhex(a['hash']))!=32:raise ValueError('Invalid password hash')
    return accounts

class AccessMiddleware(BaseHTTPMiddleware):
    def __init__(self,app,settings):
        super().__init__(app);self.settings=settings;self.accounts=load_accounts(settings.auth_file);self.failures=defaultdict(deque)
        if settings.deployment=='production' and not self.accounts:raise ValueError('Production authentication is required')
    async def dispatch(self,request,call_next):
        # Liveness contains no account, invoice, storage or provider details.
        if self.accounts and request.url.path=='/livez':return JSONResponse({'status':'ok'})
        request.state.principal=None
        if self.accounts:
            peer=request.client.host if request.client else 'unknown';now=time.monotonic();failures=self.failures[peer]
            while failures and now-failures[0]>60:failures.popleft()
            if len(failures)>=10:return JSONResponse({'error':{'code':'login_rate_limit','message':'Too many failed sign-ins. Try again in one minute.'}},status_code=429,headers={'Retry-After':'60'})
            header=request.headers.get('authorization','');user=password=''
            try:
                scheme,token=header.split(' ',1)
                if scheme.lower()=='basic' and len(token)<4096:user,password=base64.b64decode(token,validate=True).decode().split(':',1)
            except (ValueError,UnicodeError):pass
            account=self.accounts.get(user);salt=account['salt'] if account else '00'*16
            actual=password_hash(password,salt);expected=account['hash'] if account else '00'*32
            if not account or not hmac.compare_digest(actual,expected):
                if header:failures.append(now)
                # Bound the in-memory limiter; a proxy should also enforce rate limits.
                if len(self.failures)>10000:self.failures.clear()
                return JSONResponse({'error':{'code':'authentication_required','message':'Sign in to access invoice data.'}},status_code=401,headers={'WWW-Authenticate':'Basic realm="Invoice review", charset="UTF-8"'})
            request.state.principal={'name':user,'role':account['role']}
            if request.method not in {'GET','HEAD','OPTIONS'}:
                if account['role']=='viewer':return JSONResponse({'error':{'code':'read_only','message':'This account has read-only access.'}},status_code=403)
                if request.url.path.startswith('/v1/purchase-orders/import') and account['role']!='admin':return JSONResponse({'error':{'code':'admin_required','message':'An administrator must import purchase orders.'}},status_code=403)
        if request.method not in {'GET','HEAD','OPTIONS'}:
            origin=request.headers.get('origin');site=request.headers.get('sec-fetch-site')
            expected=self.settings.public_origin.rstrip('/') or str(request.base_url).rstrip('/')
            if site=='cross-site' or (origin and origin.rstrip('/')!=expected):
                return JSONResponse({'error':{'code':'cross_site_request','message':'Cross-site writes are not allowed.'}},status_code=403)
        response=await call_next(request)
        if self.settings.deployment=='production':response.headers['Strict-Transport-Security']='max-age=31536000'
        response.headers['Referrer-Policy']='no-referrer'
        return response

def install_security(app,settings):
    hosts=[h.strip() for h in settings.allowed_hosts.split(',') if h.strip()]
    if not hosts or '*' in hosts:raise ValueError('Explicit allowed hostnames are required')
    # Parse credentials now so a bad deployment fails startup, not its first request.
    load_accounts(settings.auth_file)
    app.add_middleware(AccessMiddleware,settings=settings)
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=hosts)

def audit_identity(request,action):
    principal=getattr(request.state,'principal',None)
    if principal:action.actor=principal['name']
    return action
