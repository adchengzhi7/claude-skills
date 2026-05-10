"""把解析過的 trip + 確認過的公司 → 重命名 + 歸檔到 ~/Downloads/uber_receipts/

目錄結構：
    ~/Downloads/uber_receipts/
      2026-04/
        2026-04-29-1238-北屯-烏日高鐵-NTD482-[我的公司].pdf
        2026-04-29-1812-烏日-內湖-NTD650-[我的公司].pdf
        2026-04-30-2342-信義-大安-NTD180-[私人].pdf
        _refunded/
          2026-04-15-0830-中山-松機-NTD420.pdf
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

ARCHIVE_ROOT = Path.home() / "Downloads" / "uber_receipts"


def _safe(s: str | None) -> str:
    if not s:
        return "未知"
    s = s.replace("/", "-").replace("\\", "-")
    return re.sub(r"[\\/:*?\"<>|\s]+", "", s)


def compute_filename(trip: dict[str, Any], company_label: str | None) -> str:
    """產生最終檔名 — YYYY-MM-DD-HHMM-起-訖-NTDXXX-[公司].<ext>

    副檔名延用原始檔（PDF 或 .eml），讓 source_path 指什麼就保留什麼。
    """
    date = trip.get("trip_date") or "未知日期"
    hhmm = (trip.get("trip_time_start") or "0000").replace(":", "")
    frm = _safe(trip.get("from_short"))
    to = _safe(trip.get("to_short"))
    amount = trip.get("total")
    amount_str = f"NTD{amount}" if amount is not None else "NTD未知"

    base = f"{date}-{hhmm}-{frm}-{to}-{amount_str}"
    if company_label:
        base += f"-[{_safe(company_label)}]"

    src = trip.get("source_path") or ""
    ext = Path(src).suffix.lower() if src else ".pdf"
    if ext not in (".pdf", ".eml", ".html"):
        ext = ".pdf"
    return f"{base}{ext}"


def compute_target_dir(trip: dict[str, Any]) -> Path:
    """月/日 階層。退款行程進 _refunded/。"""
    date = trip.get("trip_date")
    if date and re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        month = date[:7]
        day_dir = date  # YYYY-MM-DD
    else:
        month = "未知月份"
        day_dir = "未知日期"
    base = ARCHIVE_ROOT / month / day_dir
    if trip.get("is_refunded"):
        base = ARCHIVE_ROOT / month / "_refunded" / day_dir
    return base


def _trip_prefix(trip: dict[str, Any], company_label: str | None) -> str:
    """每趟的檔名 prefix（不含 role）：HHMM-起-訖-NTDXXX-[公司]"""
    hhmm = (trip.get("trip_time_start") or "0000").replace(":", "")
    frm = _safe(trip.get("from_short"))
    to = _safe(trip.get("to_short"))
    amount = trip.get("total")
    amount_str = f"NTD{amount}" if amount is not None else "NTD未知"
    base = f"{hhmm}-{frm}-{to}-{amount_str}"
    if company_label:
        base += f"-[{_safe(company_label)}]"
    return base


def organize_trip(
    trip: dict[str, Any],
    company_label: str | None,
    *,
    move: bool = True,
    overwrite: bool = False,
    keep_eml: bool = False,
    keep_xml: bool = False,
) -> dict[str, Any]:
    """把一趟 trip 相關檔案歸檔到 月/日 資料夾。

    預設只留 PDF（行程明細 + 發票 PDF）— 報帳常用格式。
      - _detail_pdf            → {prefix}-行程明細.pdf
      - _invoices[*].pdf       → {prefix}-發票-{InvoiceNumber}.pdf
      - _invoices[*].xml       → {prefix}-發票-{InvoiceNumber}.xml（如 keep_xml）
      - source_path（.eml）    → {prefix}-信件.eml（如 keep_eml）

    XML 仍會被讀取以抽出發票號碼用於命名，但預設不歸檔。

    回傳 {"actions": [{"src", "dst", "action"}], "trip_dir": str}.
    """
    target_dir = compute_target_dir(trip)
    target_dir.mkdir(parents=True, exist_ok=True)
    prefix = _trip_prefix(trip, company_label)

    actions: list[dict[str, str]] = []

    # 找一張 XML 抽發票號碼（給命名用）
    invoice_number: str | None = None
    sys_path_inserted = False
    try:
        for inv in trip.get("_invoices", []):
            if inv.get("ext") == ".xml" and inv.get("path"):
                if not sys_path_inserted:
                    import sys
                    sys.path.insert(0, str(Path(__file__).parent))
                    sys_path_inserted = True
                from email_parser import parse_xml_invoice
                meta = parse_xml_invoice(inv["path"])
                invoice_number = meta.get("invoice_number")
                if invoice_number:
                    break
    except Exception:
        pass

    def _do(src_path: str | Path | None, target_name: str):
        if not src_path:
            return
        src = Path(src_path).expanduser()
        if not src.exists():
            return
        dst = target_dir / target_name
        if dst.exists():
            if dst.resolve() == src.resolve():
                actions.append({"src": str(src), "dst": str(dst), "action": "skipped_same"})
                return
            if not overwrite:
                actions.append({"src": str(src), "dst": str(dst), "action": "skipped_exists"})
                return
            action = "overwritten"
        else:
            action = "moved" if move else "copied"
        if move:
            shutil.move(str(src), str(dst))
        else:
            shutil.copy2(src, dst)
        actions.append({"src": str(src), "dst": str(dst), "action": action})

    # 1. 行程明細 PDF
    _do(trip.get("_detail_pdf"), f"{prefix}-行程明細.pdf")

    # 2. 統一發票（預設只留 PDF；XML 用於 invoice_number 但不歸檔）
    invs = trip.get("_invoices", []) or []
    for i, inv in enumerate(invs, 1):
        ext = inv.get("ext") or ".bin"
        if ext == ".xml" and not keep_xml:
            continue
        if invoice_number:
            tag = f"發票-{invoice_number}"
        else:
            tag = f"發票-{i}"
        _do(inv.get("path"), f"{prefix}-{tag}{ext}")

    # 3. 原始信件 .eml（可選）
    if keep_eml:
        _do(trip.get("source_path"), f"{prefix}-信件.eml")

    return {"actions": actions, "trip_dir": str(target_dir), "prefix": prefix}


def organize(
    trip: dict[str, Any],
    company_label: str | None,
    *,
    move: bool = True,
    overwrite: bool = False,
) -> dict[str, Any]:
    """歸檔。company_label 可為 None（未分類）/ "私人" / 公司 label。

    回傳 {"action": "moved"|"copied"|"skipped"|"overwritten", "target": str, ...}。
    """
    src = Path(trip["source_path"]).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(f"原始檔不存在: {src}")

    target_dir = compute_target_dir(trip)
    target_dir.mkdir(parents=True, exist_ok=True)

    filename = compute_filename(trip, company_label)
    target = target_dir / filename

    if target.exists() and target.resolve() == src.resolve():
        return {"action": "skipped", "target": str(target), "reason": "已是目標路徑"}

    if target.exists() and not overwrite:
        return {"action": "skipped", "target": str(target), "reason": "目標檔已存在（用 overwrite=True 強制覆蓋）"}

    action = "overwritten" if target.exists() else ("moved" if move else "copied")

    if move:
        shutil.move(str(src), str(target))
    else:
        shutil.copy2(src, target)

    return {"action": action, "target": str(target), "source": str(src)}
