"""NEXUS dashboard API and web shell. Run only on 127.0.0.1 without authentication."""
import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import db
from .adapters import is_supported
from .runner import runner

BASE=Path(__file__).resolve().parent
@asynccontextmanager
async def lifespan(app:FastAPI):
    db.init()
    yield
    await runner.shutdown()

app=FastAPI(title='NEXUS Commerce Operations',version='0.2.0',lifespan=lifespan,docs_url=None,redoc_url=None)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','[::1]','testserver'])
app.mount('/static',StaticFiles(directory=BASE/'static'),name='static')

@app.middleware('http')
async def protect_mutations(request:Request,call_next):
    if request.url.path.startswith('/api/') and request.method in ('POST','PATCH','PUT','DELETE'):
        if request.headers.get('X-Nexus-Request')!='dashboard':
            return JSONResponse({'detail':'同一オリジンのダッシュボードから操作してください'},status_code=403)
        origin=request.headers.get('origin')
        if origin:
            try:
                u=urlsplit(origin)
                host=request.headers.get('host','')
                if u.netloc.lower()!=host.lower():
                    return JSONResponse({'detail':'異なるオリジンからの操作は拒否しました'},status_code=403)
            except Exception:
                return JSONResponse({'detail':'不正なOrigin'},status_code=403)
    return await call_next(request)

class TaskData(BaseModel):
    site_key:str=Field(min_length=1,max_length=32)
    group_name:str=Field(default='default',max_length=60)
    product_url:str=Field(default='',max_length=1800)
    keyword:str=Field(default='',max_length=300)
    qty:int=Field(default=1,ge=1,le=10)
    profile_id:int|None=None
    mode:Literal['monitor','monitor_handoff']='monitor'
    @field_validator('product_url')
    @classmethod
    def url_or_empty(cls,v):
        v=v.strip()
        if v:
            u=urlsplit(v)
            if u.scheme not in ('http','https') or not u.hostname or u.username or u.password:
                raise ValueError('http(s)の商品URLを入力してください')
        return v
    @field_validator('group_name','keyword')
    @classmethod
    def trimmed(cls,v):return v.strip()

class TaskPatch(BaseModel):
    site_key:str|None=Field(default=None,max_length=32)
    group_name:str|None=Field(default=None,max_length=60)
    product_url:str|None=Field(default=None,max_length=1800)
    keyword:str|None=Field(default=None,max_length=300)
    qty:int|None=Field(default=None,ge=1,le=10)
    profile_id:int|None=None
    mode:Literal['monitor','monitor_handoff']|None=None

class ProfileData(BaseModel):
    name:str=Field(min_length=1,max_length=100)
    recipient:str=Field(default='',max_length=100)
    postal:str=Field(default='',max_length=30)
    address:str=Field(default='',max_length=300)
    phone:str=Field(default='',max_length=40)
    email:str=Field(default='',max_length=150)
    payment_label:str=Field(default='',max_length=120)

class SiteData(BaseModel):
    enabled:bool
    interval_sec:int=Field(ge=10,le=3600)

class BulkData(BaseModel):
    action:Literal['start','stop','delete']
    ids:list[int]=Field(default_factory=list,max_length=200)


def ensure_task(tid):
    with db.conn() as c:
        row=c.execute('SELECT * FROM tasks WHERE id=?',(tid,)).fetchone()
    if row is None:raise HTTPException(404,'タスクが見つかりません')
    return dict(row)

def ensure_site(key):
    with db.conn() as c:
        row=c.execute('SELECT * FROM sites WHERE key=?',(key,)).fetchone()
    if row is None:raise HTTPException(400,'サイトが見つかりません')
    return dict(row)

def ensure_profile(pid):
    if pid is None:return
    with db.conn() as c:
        exists=c.execute('SELECT 1 FROM profiles WHERE id=?',(pid,)).fetchone()
    if not exists:raise HTTPException(400,'プロファイルが見つかりません')

@app.get('/api/health')
def health():return {'ok':True,'mode':'demo' if os.getenv('DEMO_MODE')=='1' else 'integration-required'}

@app.get('/api/state')
def state():
    payload=db.dashboard()
    payload['demo_mode']=os.getenv('DEMO_MODE','0')=='1'
    payload['live_integrations']=[s['key'] for s in payload['sites'] if is_supported(s['key'])]
    payload['running_ids']=[k for k in runner.jobs if runner.is_running(k)]
    payload['runner_active']=len(payload['running_ids'])
    return payload

@app.get('/api/logs')
def logs(task_id:int|None=None,level:str='',limit:int=Query(default=200,ge=1,le=1000)):
    query='SELECT * FROM logs WHERE 1=1'; args=[]
    if task_id is not None:query+=' AND task_id=?';args.append(task_id)
    if level in ('info','warn','error','success'):query+=' AND level=?';args.append(level)
    query+=' ORDER BY id DESC LIMIT ?';args.append(limit)
    with db.conn() as c:
        return [dict(x) for x in c.execute(query,args)]

@app.post('/api/tasks',status_code=201)
def add_task(body:TaskData):
    ensure_site(body.site_key)
    ensure_profile(body.profile_id)
    if not body.product_url and not body.keyword:raise HTTPException(422,'商品URLまたはキーワードが必要です')
    with db.conn() as c:
        cur=c.execute('''INSERT INTO tasks(group_name,site_key,product_url,keyword,qty,profile_id,mode,status,status_msg,updated_at)
          VALUES(?,?,?,?,?,?,?,?,?,?)''',(body.group_name or 'default',body.site_key,body.product_url,body.keyword,body.qty,body.profile_id,body.mode,'idle','未開始',db.now()))
        tid=cur.lastrowid
    db.log(tid,'info','タスクを作成')
    return {'id':tid}

@app.patch('/api/tasks/{tid}')
def edit_task(tid:int,body:TaskPatch):
    prior=ensure_task(tid)
    data=body.model_dump(exclude_unset=True)
    if not data:return {'id':tid}
    merged={**prior,**data}
    try:validated=TaskData(**{k:merged.get(k) for k in TaskData.model_fields})
    except Exception as e:raise HTTPException(422,'タスクの入力値を確認してください') from e
    if not validated.product_url and not validated.keyword:raise HTTPException(422,'商品URLまたはキーワードが必要です')
    ensure_site(validated.site_key);ensure_profile(validated.profile_id)
    if runner.is_running(tid):runner.stop(tid)
    allowed=list(TaskData.model_fields.keys())
    with db.conn() as c:
        c.execute('UPDATE tasks SET '+','.join(f'{key}=?' for key in allowed)+',status=?,status_msg=?,updated_at=? WHERE id=?',
          [getattr(validated,key) for key in allowed]+['idle','編集済み · 再開始してください',db.now(),tid])
    db.log(tid,'info','タスクを更新')
    return {'id':tid}

@app.delete('/api/tasks/{tid}')
def delete_task(tid:int):
    ensure_task(tid)
    if runner.is_running(tid):runner.stop(tid)
    with db.conn() as c:
        c.execute('DELETE FROM tasks WHERE id=?',(tid,))
    db.log(tid,'info','タスクを削除')
    return {'deleted':tid}

@app.post('/api/tasks/{tid}/start')
async def start_task(tid:int):
    ensure_task(tid)
    try:started=runner.start(tid)
    except ValueError as e:raise HTTPException(409,str(e)) from e
    return {'started':started}

@app.post('/api/tasks/{tid}/stop')
async def stop_task(tid:int):
    ensure_task(tid)
    return {'stopped':runner.stop(tid)}

@app.post('/api/tasks/bulk')
async def bulk(body:BulkData):
    results={'ok':[],'failed':[]}
    for tid in list(dict.fromkeys(body.ids)):
        try:
            ensure_task(tid)
            if body.action=='start':runner.start(tid)
            if body.action=='stop':runner.stop(tid)
            if body.action=='delete':
                if runner.is_running(tid):runner.stop(tid)
                with db.conn() as c:c.execute('DELETE FROM tasks WHERE id=?',(tid,))
                db.log(tid,'info','タスクを削除')
            results['ok'].append(tid)
        except (HTTPException,ValueError) as e:
            results['failed'].append({'id':tid,'reason':str(e.detail) if isinstance(e,HTTPException) else str(e)})
    return results

@app.post('/api/profiles',status_code=201)
def add_profile(body:ProfileData):
    with db.conn() as c:
        cur=c.execute('INSERT INTO profiles(name,recipient,postal,address,phone,email,payment_label) VALUES(?,?,?,?,?,?,?)',tuple(body.model_dump().values()))
    return {'id':cur.lastrowid}

@app.patch('/api/profiles/{pid}')
def edit_profile(pid:int,body:ProfileData):
    ensure_profile(pid)
    with db.conn() as c:
        c.execute('UPDATE profiles SET '+','.join(f'{key}=?' for key in body.model_fields)+' WHERE id=?',list(body.model_dump().values())+[pid])
    return {'id':pid}

@app.delete('/api/profiles/{pid}')
def delete_profile(pid:int):
    ensure_profile(pid)
    with db.conn() as c:
        c.execute('UPDATE tasks SET profile_id=NULL WHERE profile_id=?',(pid,))
        c.execute('DELETE FROM profiles WHERE id=?',(pid,))
    return {'deleted':pid}

@app.patch('/api/sites/{key}')
def edit_site(key:str,body:SiteData):
    ensure_site(key)
    with db.conn() as c:
        c.execute('UPDATE sites SET enabled=?,interval_sec=? WHERE key=?',(int(body.enabled),body.interval_sec,key))
        affected=[r[0] for r in c.execute('SELECT id FROM tasks WHERE site_key=?',(key,))]
    if not body.enabled:
        for tid in affected:
            if runner.is_running(tid):runner.stop(tid)
    return {'key':key}

@app.get('/api/export')
def export_config():
    data=db.dashboard()
    # Explicitly do not export addresses, email, phone, profile recipient or any secrets.
    return {'format':'nexus-config-v1','sites':[{'key':s['key'],'enabled':s['enabled'],'interval_sec':s['interval_sec']} for s in data['sites']],
            'tasks':[{k:t[k] for k in ('group_name','site_key','product_url','keyword','qty','mode')} for t in data['tasks']]}

@app.get('/')
@app.get('/tasks')
@app.get('/profiles')
@app.get('/sites')
@app.get('/logs')
@app.get('/settings')
def shell():return FileResponse(BASE/'static'/'index.html')
