"""Public accounts with opaque cookie sessions and isolated invoice schemas."""
import base64,hashlib,hmac,json,re,secrets,time,uuid
from datetime import datetime,timezone
from fastapi.responses import JSONResponse,Response
from starlette.concurrency import run_in_threadpool
from invoice_intelligence.security import password_hash
from invoice_intelligence.cloud.postgres import TENANT

SESSION='__Host-invoice_session'
VISITOR='__Host-invoice_visitor'
DAYS=7*86400

def initialize(store):
    with store.pool.connection() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS public.site_users (
          id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,salt TEXT NOT NULL,password_hash TEXT NOT NULL,
          outreach BOOLEAN NOT NULL DEFAULT FALSE,outreach_at DOUBLE PRECISION,created_at DOUBLE PRECISION NOT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS public.site_sessions (
          digest TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES public.site_users(id),expires DOUBLE PRECISION NOT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS public.site_admin_sessions (digest TEXT PRIMARY KEY,name TEXT NOT NULL,expires DOUBLE PRECISION NOT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS public.site_limits (key TEXT PRIMARY KEY,count INTEGER NOT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS public.site_visitors (
          id TEXT PRIMARY KEY,first_seen DOUBLE PRECISION NOT NULL,last_seen DOUBLE PRECISION NOT NULL,visits INTEGER NOT NULL DEFAULT 1)''')

def limit(store,key,maximum):
    day=datetime.now(timezone.utc).strftime('%Y-%m-%d')
    with store.pool.connection() as c:
        row=c.execute('''INSERT INTO public.site_limits(key,count) VALUES (%s,1)
            ON CONFLICT (key) DO UPDATE SET count=site_limits.count+1 RETURNING count''',(day+':'+key,)).fetchone()
    return row['count']<=maximum

def cookie(response,name,value,age):
    response.set_cookie(name,value,max_age=age,secure=True,httponly=True,samesite='lax',path='/')

def error(message,status=400):return JSONResponse({'error':{'message':message}},status_code=status)

def principal(store,request,accounts):
    raw=request.cookies.get(SESSION,'')
    if raw and len(raw)<200:
        with store.pool.connection() as c:
            row=c.execute('''SELECT u.id,u.email,u.outreach FROM public.site_sessions s
              JOIN public.site_users u ON s.user_id=u.id WHERE s.digest=%s AND s.expires>%s''',
              (hashlib.sha256(raw.encode()).hexdigest(),time.time())).fetchone()
        if not row:
            with store.pool.connection() as c:admin=c.execute('SELECT name FROM public.site_admin_sessions WHERE digest=%s AND expires>%s',(hashlib.sha256(raw.encode()).hexdigest(),time.time())).fetchone()
            if admin and admin['name'] in accounts:return {'name':admin['name'],'role':accounts[admin['name']]['role'],'tenant':None}
        if row:return {'name':row['email'],'role':'admin','tenant':'tenant_'+row['id'],'id':row['id'],'outreach':row['outreach']}
    header=request.headers.get('authorization','')
    if header:
        try:
            scheme,token=header.split(' ',1)
            if scheme.lower()=='basic' and len(token)<4096:
                name,password=base64.b64decode(token,validate=True).decode().split(':',1)
                a=accounts.get(name)
                actual=password_hash(password,a['salt'] if a else '00'*16)
                if a and hmac.compare_digest(actual,a['hash']):return {'name':name,'role':a['role'],'tenant':None}
        except (ValueError,UnicodeError):pass
    return None

def auth_action(store,request,body,p,accounts):
    path=request.url.path;now=time.time()
    if path=='/v1/auth/me' and request.method=='GET':
        return JSONResponse({'user':p['name'],'outreach':p.get('outreach',False),'site_admin':p['role']=='admin' and not p.get('tenant')} if p else {'user':None})
    if path=='/v1/auth/logout' and request.method=='POST':
        raw=request.cookies.get(SESSION,'')
        with store.pool.connection() as c:
            c.execute('DELETE FROM public.site_sessions WHERE digest=%s',(hashlib.sha256(raw.encode()).hexdigest(),))
            c.execute('DELETE FROM public.site_admin_sessions WHERE digest=%s',(hashlib.sha256(raw.encode()).hexdigest(),))
        r=JSONResponse({'ok':True});r.delete_cookie(SESSION,secure=True,httponly=True,samesite='lax');return r
    if path in {'/v1/auth/signup','/v1/auth/login'} and request.method=='POST':
        peer=hashlib.sha256((request.client.host if request.client else 'unknown').encode()).hexdigest()
        if not limit(store,'auth:'+peer,40):return error('Too many attempts today. Please try again later.',429)
        email=body.get('email','');password=body.get('password','')
        if not isinstance(email,str) or not isinstance(password,str):return error('Enter an email and password.')
        email=email.strip().lower()
        if path.endswith('login') and email in accounts:
            a=accounts[email]
            if not 12<=len(password)<=128 or not hmac.compare_digest(password_hash(password,a['salt']),a['hash']):return error('Email or password is incorrect.',401)
            raw=secrets.token_urlsafe(32)
            with store.pool.connection() as c:
                c.execute('DELETE FROM public.site_admin_sessions WHERE expires<%s',(now,))
                c.execute('INSERT INTO public.site_admin_sessions(digest,name,expires) VALUES (%s,%s,%s)',(hashlib.sha256(raw.encode()).hexdigest(),email,now+DAYS))
            r=JSONResponse({'user':email});cookie(r,SESSION,raw,DAYS);return r
        if len(email)>254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email) or not 12<=len(password)<=128:
            return error('Use a valid email and a password of 12–128 characters.')
        if path.endswith('signup'):
            if not limit(store,'signups',100):return error('New registrations are temporarily full. Please return tomorrow.',429)
            identifier=uuid.uuid4().hex;salt=secrets.token_hex(16)
            outreach=body.get('outreach') is True
            with store.pool.connection() as c:
                inserted=c.execute('''INSERT INTO public.site_users(id,email,salt,password_hash,outreach,outreach_at,created_at)
                 VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(email) DO NOTHING RETURNING id''',
                 (identifier,email,salt,password_hash(password,salt),outreach,now if outreach else None,now)).fetchone()
            if not inserted:return error('Unable to create account. Try signing in instead.',409)
            # Identifiers are generated on the server; no client-controlled SQL names.
            from psycopg import sql
            with store.pool.connection() as c:c.execute(sql.SQL('CREATE SCHEMA IF NOT EXISTS {}').format(sql.Identifier('tenant_'+identifier)))
            token=TENANT.set('tenant_'+identifier)
            try:store.initialize()
            finally:TENANT.reset(token)
        else:
            with store.pool.connection() as c:row=c.execute('SELECT * FROM public.site_users WHERE email=%s',(email,)).fetchone()
            actual=password_hash(password,row['salt'] if row else '00'*16)
            if not row or not hmac.compare_digest(actual,row['password_hash']):return error('Email or password is incorrect.',401)
            identifier=row['id']
            from psycopg import sql
            with store.pool.connection() as c:c.execute(sql.SQL('CREATE SCHEMA IF NOT EXISTS {}').format(sql.Identifier('tenant_'+identifier)))
            token=TENANT.set('tenant_'+identifier)
            try:store.initialize()
            finally:TENANT.reset(token)
        raw=secrets.token_urlsafe(32)
        with store.pool.connection() as c:
            c.execute('DELETE FROM public.site_sessions WHERE expires<%s',(now,))
            c.execute('INSERT INTO public.site_sessions(digest,user_id,expires) VALUES (%s,%s,%s)',(hashlib.sha256(raw.encode()).hexdigest(),identifier,now+DAYS))
        r=JSONResponse({'user':email});cookie(r,SESSION,raw,DAYS);return r
    if path=='/v1/auth/outreach' and request.method=='POST':
        if not p or not p.get('id'):return error('Sign in to update your preference.',401)
        allowed=body.get('allowed') is True
        with store.pool.connection() as c:c.execute('UPDATE public.site_users SET outreach=%s,outreach_at=%s WHERE id=%s',(allowed,now if allowed else None,p['id']))
        return JSONResponse({'outreach':allowed})
    if path=='/v1/auth/consent' and request.method=='POST':
        r=JSONResponse({'analytics':body.get('analytics') is True})
        if body.get('analytics') is True:
            identifier=secrets.token_urlsafe(24)
            with store.pool.connection() as c:c.execute('INSERT INTO public.site_visitors(id,first_seen,last_seen) VALUES (%s,%s,%s)',(identifier,now,now))
            cookie(r,VISITOR,identifier,180*86400)
        else:
            with store.pool.connection() as c:c.execute('DELETE FROM public.site_visitors WHERE id=%s',(request.cookies.get(VISITOR,''),))
            r.delete_cookie(VISITOR,secure=True,httponly=True,samesite='lax')
        return r
    if path=='/v1/auth/visit' and request.method=='POST':
        with store.pool.connection() as c:
            c.execute('DELETE FROM public.site_visitors WHERE last_seen<%s',(now-180*86400,))
            c.execute('UPDATE public.site_visitors SET last_seen=%s,visits=visits+1 WHERE id=%s',(now,request.cookies.get(VISITOR,'')))
        return JSONResponse({'ok':True})
    if path=='/v1/admin/audience.xlsx' and request.method=='GET':
        if not p or p.get('tenant') or p['role']!='admin':return error('Site administrator access required.',403)
        from invoice_intelligence.persistence.xlsx import workbook
        with store.pool.connection() as c:
            leads=c.execute('SELECT email,outreach_at FROM public.site_users WHERE outreach=TRUE ORDER BY outreach_at DESC').fetchall()
            stats=c.execute('SELECT count(*) AS visitors,coalesce(sum(visits),0) AS visits FROM public.site_visitors').fetchone()
        data=workbook([('Opted-in contacts',[['Email','Consent timestamp (UTC)','Email verified'],*[[x['email'],datetime.fromtimestamp(x['outreach_at'],timezone.utc).isoformat(),'No'] for x in leads]]),('Visitor totals',[['Consented visitors','Visits'],[stats['visitors'],stats['visits']]])])
        return Response(data,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename="consented_audience.xlsx"'})
    return error('Not found.',404)

async def dispatch(middleware,request,call_next):
    store=request.app.state.store;path=request.url.path
    if request.method not in {'GET','HEAD','OPTIONS'}:
        origin=request.headers.get('origin');expected=middleware.settings.public_origin.rstrip('/')
        if request.headers.get('sec-fetch-site')=='cross-site' or (origin and origin.rstrip('/')!=expected):return error('Cross-site writes are not allowed.',403)
    if path in {'/v1/auth/consent','/v1/auth/visit'} and request.method=='POST':
        peer=hashlib.sha256((request.client.host if request.client else 'unknown').encode()).hexdigest()
        if not await run_in_threadpool(limit,store,'visitor:'+peer,100):return error('Please try again tomorrow.',429)
    p=await run_in_threadpool(principal,store,request,middleware.accounts)
    request.state.principal=p
    if path.startswith('/v1/auth/') or path=='/v1/admin/audience.xlsx':
        body={}
        if request.method=='POST':
            raw=await request.body()
            if len(raw)>4096:return error('Request too large.',413)
            try:body=json.loads(raw or b'{}')
            except (ValueError,UnicodeError):return error('Invalid request.')
            if not isinstance(body,dict):return error('Invalid request.')
        return await run_in_threadpool(auth_action,store,request,body,p,middleware.accounts)
    public=request.method in {'GET','HEAD'} and (path in {'/','/login','/privacy','/favicon.svg','/favicon.ico','/livez'} or path.startswith('/assets/'))
    if not p and not public:return error('Sign in to access your invoices.',401)
    if p and p['role']=='viewer' and request.method not in {'GET','HEAD','OPTIONS'}:return error('Read-only account.',403)
    tenant=TENANT.set(p.get('tenant') if p else None)
    try:
        if p and p.get('tenant') and request.method=='POST' and path=='/v1/documents':
            if not await run_in_threadpool(limit,store,'uploads:'+p['id'],10):return error('Your daily limit is 10 uploads. Please return tomorrow.',429)
        if p and p.get('tenant') and request.method=='POST' and path.endswith('/process'):
            if not await run_in_threadpool(limit,store,'processing',200):return error('Today’s demo processing limit has been reached.',429)
        response=await call_next(request)
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Strict-Transport-Security']='max-age=31536000'
        return response
    finally:TENANT.reset(tenant)
