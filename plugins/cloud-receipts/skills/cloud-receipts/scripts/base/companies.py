"""共用公司清單載入器（cloud-receipts / uber-receipt / thsr-receipt 三者共享）。

讀取優先順序：
    1. ~/.config/receipts/companies.json（共用主要位置）
    2. ~/.config/thsr-receipt/companies.json（legacy fallback，自動 migrate）
    3. ~/.config/tra-receipt/companies.json（legacy fallback）
    4. 都沒有 → 回傳 []
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

PRIMARY_PATH = Path.home() / ".config" / "receipts" / "companies.json"
LEGACY_PATHS = [
    Path.home() / ".config" / "thsr-receipt" / "companies.json",
    Path.home() / ".config" / "tra-receipt" / "companies.json",
]


def _read_json(path: Path) -> list[dict] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [c for c in data if isinstance(c, dict) and {"tax_id", "name", "label"} <= c.keys()]
    except Exception:
        return None
    return None


def _migrate_from_legacy() -> list[dict] | None:
    for legacy in LEGACY_PATHS:
        data = _read_json(legacy)
        if data:
            PRIMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(legacy, PRIMARY_PATH)
            try:
                PRIMARY_PATH.chmod(0o600)
            except OSError:
                pass
            return data
    return None


def load_companies() -> list[dict]:
    data = _read_json(PRIMARY_PATH)
    if data is not None:
        return data
    migrated = _migrate_from_legacy()
    return migrated if migrated else []


def get_company(label: str) -> dict | None:
    for c in load_companies():
        if c["label"] == label:
            return c
    return None


def get_company_by_tax_id(tax_id: str) -> dict | None:
    for c in load_companies():
        if c["tax_id"] == tax_id:
            return c
    return None


def write_companies(companies: list[dict]) -> None:
    PRIMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRIMARY_PATH.write_text(
        json.dumps(companies, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    try:
        PRIMARY_PATH.chmod(0o600)
    except OSError:
        pass


def list_summary() -> str:
    companies = load_companies()
    if not companies:
        return f"📋 {PRIMARY_PATH} 不存在"
    lines = [f"📋 {PRIMARY_PATH} ({len(companies)} 筆):"]
    for c in companies:
        lines.append(f"   • {c['label']}  [統編 {c['tax_id']}]  {c['name']}")
    return "\n".join(lines)
