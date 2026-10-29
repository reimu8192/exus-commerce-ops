"""Bounded, cancel-safe monitoring. No automatic cart/checkout action."""
import asyncio
import os
import time
import httpx
from . import db
from .adapters import get_adapter,is_supported

class Runner:
    def __init__(self):
        self.jobs={}
        self.global_slots=asyncio.Semaphore(4)
        self.site_locks={}
        self.last_check={}

    def is_running(self,tid):
        t=self.jobs.get(tid)
        return t is not None and not t.done()

    def start(self,tid):
        if self.is_running(tid):return False
        with db.conn() as c:
            task=c.execute('SELECT t.id,t.site_key,s.enabled FROM tasks t JOIN sites s ON s.key=t.site_key WHERE t.id=?',(tid,)).fetchone()
        if task is None: raise ValueError('タスクが見つかりません')
        if not task['enabled']:raise ValueError('このサイトは無効になっています')
        if not is_supported(task['site_key']):raise ValueError('監視アダプタが未接続です。DEMO_MODE=1 で動作確認できます')
        db.set_status(tid,'queued','実行キューに追加')
        job=asyncio.create_task(self._loop(tid))
        self.jobs[tid]=job
        def cleanup(done):
            if self.jobs.get(tid) is done:self.jobs.pop(tid,None)
        job.add_done_callback(cleanup)
        return True

    def stop(self,tid):
        job=self.jobs.pop(tid,None)
        if job and not job.done():job.cancel()
        with db.conn() as c:
            exists=c.execute('SELECT 1 FROM tasks WHERE id=?',(tid,)).fetchone()
        if exists:
            db.set_status(tid,'stopped','手動停止')
            db.log(tid,'info','監視を停止')
        return bool(job)

    async def shutdown(self):
        jobs=list(self.jobs.values())
        for job in jobs:job.cancel()
        if jobs:await asyncio.gather(*jobs,return_exceptions=True)
        self.jobs.clear()

    async def _notify(self,site,target):
        webhook=os.getenv('DISCORD_WEBHOOK_URL','')
        if not webhook or os.getenv('DEMO_MODE','0')=='1':return
        try:
            async with httpx.AsyncClient(timeout=8) as c:
                res=await c.post(webhook,json={'content':f'🟢 在庫を検知 [{site}] {target}'})
                res.raise_for_status()
        except Exception:
            db.log(None,'warn','Discordへの通知に失敗しました')

    async def _check_site(self,task,interval):
        key=task['site_key']
        lock=self.site_locks.setdefault(key,asyncio.Lock())
        # サイト単位の待ち（ロック・間隔調整）を先に済ませ、全体枠は実際のチェック中だけ握る。
        # 逆順だと、1サイトに多数のタスクがあるとき全体枠を待機で使い切り、他サイトが止まる。
        async with lock:
            elapsed=time.monotonic()-self.last_check.get(key,0)
            # Conservative aggregate site pacing even with many tasks.
            remaining=max(0,min(interval,60)-elapsed)
            if remaining:await asyncio.sleep(remaining)
            async with self.global_slots:
                self.last_check[key]=time.monotonic()
                return await get_adapter(key)(task)

    async def _loop(self,tid):
        try:
            with db.conn() as c:
                task=c.execute('SELECT * FROM tasks WHERE id=?',(tid,)).fetchone()
                if task is None:return
                task=dict(task)
                site=c.execute('SELECT * FROM sites WHERE key=?',(task['site_key'],)).fetchone()
                if site is None or not site['enabled']:
                    db.set_status(tid,'error','サイトが無効です');return
                interval=max(10,int(site['interval_sec']))
                site_name=site['name']
            db.set_status(tid,'watching',f'{interval}秒間隔で監視')
            db.log(tid,'info',f'監視開始 · {site_name}')
            backoff=interval
            while True:
                try:
                    result=await self._check_site(task,interval)
                    backoff=interval
                except asyncio.CancelledError:raise
                except NotImplementedError as e:
                    db.set_status(tid,'error',str(e));db.log(tid,'error',str(e));return
                except Exception as e:
                    backoff=min(max(backoff*2,interval),900)
                    db.set_status(tid,'error',f'通信・処理エラー。{backoff}秒後に再試行')
                    db.log(tid,'warn',f'監視チェック失敗: {type(e).__name__}')
                    await asyncio.sleep(backoff)
                    continue
                if result.in_stock:
                    state='handoff' if task['mode']=='monitor_handoff' else 'in_stock'
                    db.set_status(tid,state,'在庫検知・手動確認待ち' if state=='handoff' else result.detail)
                    db.log(tid,'success',result.detail or '在庫検知')
                    await self._notify(site_name,task['product_url'] or task['keyword'])
                    return
                db.set_status(tid,'watching',result.detail or '在庫なし')
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            # stop() writes the authoritative stopped state.
            return
        except Exception:
            db.set_status(tid,'error','監視処理で予期せぬエラーが発生しました')
            db.log(tid,'error','監視処理で予期せぬエラーが発生しました')

runner=Runner()
