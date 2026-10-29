import pytest
from httpx import ASGITransport, AsyncClient
from app import db
from app.main import app
from app.runner import runner

HEAD={'X-Nexus-Request':'dashboard'}

@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, 'DB_PATH', tmp_path/'test.db')
    monkeypatch.setenv('DEMO_MODE','1')
    monkeypatch.delenv('NEXUS_SEED_DEMO',raising=False)
    runner.jobs.clear()
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://testserver') as c:
            yield c

@pytest.mark.anyio
async def test_initial_state_and_site_list(client):
    r=await client.get('/api/state')
    assert r.status_code==200
    assert len(r.json()['sites'])>=8
    assert r.json()['tasks']==[]
    assert (await client.get('/')).status_code==200

@pytest.mark.anyio
async def test_task_crud_and_logs(client):
    params={'site_key':'geo','keyword':'新作ゲーム機','qty':2,'group_name':'Gaming','mode':'monitor'}
    r=await client.post('/api/tasks',json=params,headers=HEAD)
    assert r.status_code==201,r.text
    tid=r.json()['id']
    st=(await client.get('/api/state')).json()
    assert st['tasks'][0]['keyword']=='新作ゲーム機'
    edit=await client.patch(f'/api/tasks/{tid}',json={'keyword':'トレカBOX','qty':3},headers=HEAD)
    assert edit.status_code==200,edit.text
    st=(await client.get('/api/state')).json()
    assert st['tasks'][0]['keyword']=='トレカBOX'
    assert st['tasks'][0]['qty']==3
    assert (await client.get(f'/api/logs?task_id={tid}')).json()
    assert (await client.delete(f'/api/tasks/{tid}',headers=HEAD)).status_code==200
    assert (await client.get('/api/state')).json()['tasks']==[]

@pytest.mark.anyio
async def test_profile_and_settings(client):
    p={'name':'ローカル検証','recipient':'Test','email':'test@example.com'}
    profile=await client.post('/api/profiles',json=p,headers=HEAD)
    assert profile.status_code==201,profile.text
    pid=profile.json()['id']
    task=await client.post('/api/tasks',json={'site_key':'rakuten','keyword':'BOX','profile_id':pid},headers=HEAD)
    assert task.status_code==201
    exp=(await client.get('/api/export')).json()
    assert 'profiles' not in exp
    assert exp['tasks'][0]['keyword']=='BOX'
    assert (await client.patch('/api/sites/rakuten',json={'enabled':False,'interval_sec':120},headers=HEAD)).status_code==200
    assert (await client.post(f'/api/tasks/{task.json()["id"]}/start',headers=HEAD)).status_code==409
    assert (await client.delete(f'/api/profiles/{pid}',headers=HEAD)).status_code==200
    assert (await client.get('/api/state')).json()['tasks'][0]['profile_id'] is None

@pytest.mark.anyio
async def test_bulk_start_stop(client):
    ids=[]
    for keyword in ('A','B'):
        r=await client.post('/api/tasks',json={'site_key':'geo','keyword':keyword},headers=HEAD)
        ids.append(r.json()['id'])
    r=await client.post('/api/tasks/bulk',json={'action':'start','ids':ids},headers=HEAD)
    assert r.status_code==200 and len(r.json()['ok'])==2
    r=await client.post('/api/tasks/bulk',json={'action':'stop','ids':ids},headers=HEAD)
    assert r.status_code==200 and len(r.json()['ok'])==2
    assert len([x for x in runner.jobs if runner.is_running(x)])==0

@pytest.mark.anyio
async def test_reject_unsafe_requests(client):
    params={'site_key':'geo','keyword':'X'}
    assert (await client.post('/api/tasks',json=params)).status_code==403
    assert (await client.post('/api/tasks',json=params,headers={**HEAD,'Origin':'https://evil.example'})).status_code==403
    assert (await client.post('/api/tasks',json={'site_key':'geo','product_url':'file:///etc/passwd'},headers=HEAD)).status_code==422
    assert (await client.post('/api/tasks',json={'site_key':'unknown','keyword':'X'},headers=HEAD)).status_code==400
    assert (await client.post('/api/tasks',json={'site_key':'geo','keyword':'X','qty':-1},headers=HEAD)).status_code==422

@pytest.mark.anyio
async def test_live_without_adapter_is_rejected(client,monkeypatch):
    r=await client.post('/api/tasks',json={'site_key':'geo','keyword':'製品'},headers=HEAD)
    tid=r.json()['id']
    monkeypatch.setenv('DEMO_MODE','0')
    r=await client.post(f'/api/tasks/{tid}/start',headers=HEAD)
    assert r.status_code==409
    assert not runner.is_running(tid)
