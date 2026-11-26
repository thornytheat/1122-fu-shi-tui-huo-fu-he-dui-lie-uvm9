"""暂估台账：关账分录号与幂等过账。

同一截止点重跑时，已定稿门店保持锁定，分录号由截止点、门店与授权单
确定性派生，重复过账被跳过，不会重复生成分录。
"""
from __future__ import annotations

from hashlib import sha256
from typing import Any

from .algorithm import PAYMENT_INSTRUCTION


def entry_id(cutoff: int, shop: str, rma: str) -> str:
    digest = sha256(f'{cutoff}|{shop}|{rma}'.encode('utf-8')).hexdigest()
    return f'ACR-{digest[:16]}'


def stamp_entries(report: dict[str, Any]) -> dict[str, Any]:
    """为报告中的每条计提分录补确定性分录号，按门店与授权单排序。"""
    stamped = []
    for entry in sorted(report['entries'], key=lambda row: (row['shop'], row['rma'])):
        stamped.append({
            'entry_id': entry_id(report['cutoff'], entry['shop'], entry['rma']),
            **entry,
        })
    return {**report, 'entries': stamped}


def post_journal(report: dict[str, Any], ledger: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """把计提报告过入暂估台账，返回过账结果；同一截止点重跑不重复生成分录。"""
    ledger = list(ledger or [])
    known = {entry['entry_id'] for entry in ledger}
    stamped = stamp_entries(report)
    posted, duplicates = [], []
    for entry in stamped['entries']:
        if entry['treatment'] == PAYMENT_INSTRUCTION:
            # 已生成退款指令的授权不产生计提分录。
            continue
        if entry['entry_id'] in known:
            duplicates.append(entry['entry_id'])
            continue
        journal_entry = {
            'entry_id': entry['entry_id'],
            'cutoff': report['cutoff'],
            'shop': entry['shop'],
            'rma': entry['rma'],
            'treatment': entry['treatment'],
            'accrual_cents': entry['accrual_cents'],
            'instruction_suspended': entry['instruction_suspended'],
        }
        ledger.append(journal_entry)
        posted.append(journal_entry)
    locked_after = sorted(set(report.get('locked_shops', ())) | set(report.get('finalized_shops', ())))
    return {
        'cutoff': report['cutoff'],
        'posted': posted,
        'posted_count': len(posted),
        'duplicate_entry_ids': sorted(duplicates),
        'duplicate_count': len(duplicates),
        'locked_shops': locked_after,
        'ledger': ledger,
        'ledger_total_cents': sum(entry['accrual_cents'] for entry in ledger),
    }
