"""Explicit adapter registry. No live store automation is bundled."""
import os
import random
from dataclasses import dataclass
from typing import Awaitable, Callable

@dataclass(frozen=True)
class CheckResult:
    in_stock: bool
    detail: str = ''

async def demo_check(task:dict)->CheckResult:
    found = random.random() < 0.06
    return CheckResult(found, 'デモ: 在庫あり' if found else 'デモ: 確認完了（在庫なし）')

async def not_implemented(task:dict)->CheckResult:
    raise NotImplementedError('実サイト用アダプタは未接続です。デモモードで動作を確認できます。')

ADAPTERS:dict[str,Callable[[dict],Awaitable[CheckResult]]]={}

def get_adapter(site_key:str):
    if os.getenv('DEMO_MODE','0')=='1':
        return demo_check
    return ADAPTERS.get(site_key,not_implemented)

def is_supported(site_key:str):
    return os.getenv('DEMO_MODE','0')=='1' or site_key in ADAPTERS
