"""Provider-aware 歸檔。

歸檔目錄：~/Downloads/cloud_receipts/<provider>/YYYY-MM/
檔名：YYYY-MM-DD-<Provider>-<InvoiceNo>-<role>[-<company>].pdf
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Iterable

from .provider import BaseProvider, InvoiceRecord


def _safe(s: str | None) -> str:
    if not s:
        return ""
    return re.sub(r"[\\/:*?\"<>|]+", "-", s).strip()


def organize(
    record: InvoiceRecord,
    provider: BaseProvider,
    *,
    overwrite: bool = False,
    dry_run: bool = False,
) -> dict:
    """把 record.documents 寫到歸檔目錄。回傳 {actions, target_dir}。"""
    target_dir = provider.archive_dir(record)
    actions: list[dict] = []

    if not dry_run:
        target_dir.mkdir(parents=True, exist_ok=True)

    for doc in record.documents:
        filename = provider.filename_for(record, doc)
        target = target_dir / filename
        if target.exists() and not overwrite:
            actions.append({"target": str(target), "action": "skipped_exists"})
            continue

        if dry_run:
            actions.append({"target": str(target), "action": "would_write",
                            "size": len(doc.content)})
            continue

        action = "overwritten" if target.exists() else "created"
        target.write_bytes(doc.content)
        actions.append({"target": str(target), "action": action,
                        "size": len(doc.content)})

    return {"target_dir": str(target_dir), "actions": actions}
