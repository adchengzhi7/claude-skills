"""啟發式：給每張 trip 推薦該分配給哪家公司（或標記為私人）。

設計目的：批次處理 5-10 張收據時，先給合理建議，使用者只需要「確認 / 改」，
不必每張都從零開始想。所有建議都帶 reason 字串，UI 會顯示給使用者看。

啟發式（依優先順序）：
    1. 退款行程 → 不建議（自動歸到 _refunded/）
    2. 同日連續行程（前一趟有公司 tag，且兩趟相距 ≤ 4 小時）→ 沿用上一趟的公司
    3. 目的地是 高鐵 / 機場，同日有 thsr-receipt PDF → 推薦那張票對應的公司
    4. 重複路線（過去 90 天歷史 ≥ 3 次同 from-to，公司一致）→ 沿用
    5. 深夜（22:00-06:00）+ 起點為住家區域 → 私人候選
    6. 週末（六日）+ 非上下班時段 → 私人候選
    7. 短途（< NT$100 + 距離 < 3 km）+ 非工作時段 → 私人候選
    8. 都不符合 → 沿用 default 公司（companies.json 的 defaults.uber）
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Any

UBER_ARCHIVE = Path.home() / "Downloads" / "uber_receipts"
THSR_ARCHIVE = Path.home() / "Downloads" / "thsr_receipts"


# 已歸檔的檔名格式：YYYY-MM-DD-HHMM-起-訖-NTDXXX-[公司].pdf
ARCHIVED_PAT = re.compile(
    r"^(\d{4}-\d{2}-\d{2})-(\d{4})-([^-]+)-([^-]+)-NTD(\d+)(?:-\[([^\]]+)\])?\.pdf$"
)


def _scan_archive(archive_dir: Path) -> list[dict[str, Any]]:
    """掃 ~/Downloads/{uber,thsr}_receipts/YYYY-MM/*.pdf，回傳結構化清單。"""
    if not archive_dir.exists():
        return []
    out: list[dict[str, Any]] = []
    for month_dir in archive_dir.iterdir():
        if not month_dir.is_dir() or not re.match(r"^\d{4}-\d{2}$", month_dir.name):
            continue
        for pdf in month_dir.rglob("*.pdf"):
            m = ARCHIVED_PAT.match(pdf.name)
            if not m:
                continue
            date, hhmm, frm, to, amount, company = m.groups()
            out.append({
                "date": date,
                "time": f"{hhmm[:2]}:{hhmm[2:]}",
                "from_short": frm,
                "to_short": to,
                "total": int(amount),
                "company": company,
                "path": str(pdf),
            })
    return out


def _is_late_night(time_hhmm: str | None) -> bool:
    if not time_hhmm:
        return False
    h = int(time_hhmm.split(":")[0])
    return h >= 22 or h < 6


def _is_weekend(date_str: str | None) -> bool:
    if not date_str:
        return False
    d = dt.date.fromisoformat(date_str)
    return d.weekday() >= 5


def _is_short_trip(trip: dict) -> bool:
    if not trip.get("total") or not trip.get("distance_km"):
        return False
    return trip["total"] < 100 and trip["distance_km"] < 3


def _is_hsr_or_airport(short: str | None) -> bool:
    if not short:
        return False
    return "高鐵" in short or "機場" in short or short in ("松機", "桃機", "小港")


def _continuation_of(trip: dict, batch: list[dict]) -> dict | None:
    """同日且時間差 ≤ 4 小時的前一趟 — 取已標公司的最近一趟。"""
    if not trip.get("trip_date") or not trip.get("trip_time_start"):
        return None
    candidates = [
        t for t in batch
        if t is not trip
        and t.get("trip_date") == trip["trip_date"]
        and t.get("trip_time_start")
        and t.get("_assigned_company")
        and t["_assigned_company"] != "私人"
    ]
    if not candidates:
        return None

    def time_diff(t):
        h1, m1 = map(int, trip["trip_time_start"].split(":"))
        h2, m2 = map(int, t["trip_time_start"].split(":"))
        return abs((h1 * 60 + m1) - (h2 * 60 + m2))

    candidates.sort(key=time_diff)
    nearest = candidates[0]
    if time_diff(nearest) <= 240:
        return nearest
    return None


_THSR_FILENAME_DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})-")


def _same_day_thsr_company(trip_date: str | None) -> str | None:
    """掃 thsr-receipt 歸檔，看同一天有沒有票。

    thsr-receipt 命名沒帶公司 tag，所以從 PDF 內容讀統編 → 在 companies.json 反查 label。
    讀取失敗或對應不到任何公司就回 None（不要 fail，因為這只是建議）。
    """
    if not trip_date:
        return None
    if not THSR_ARCHIVE.exists():
        return None

    month = trip_date[:7]
    month_dir = THSR_ARCHIVE / month
    if not month_dir.exists():
        return None

    candidates = []
    for pdf in month_dir.glob("*.pdf"):
        m = _THSR_FILENAME_DATE.match(pdf.name)
        if m and m.group(1) == trip_date:
            candidates.append(pdf)

    if not candidates:
        return None

    from companies import load_companies
    companies = load_companies()
    by_tax_id = {c["tax_id"]: c["label"] for c in companies}

    try:
        import warnings
        warnings.filterwarnings("ignore")
        import pdfplumber
    except ImportError:
        return None

    for pdf in candidates:
        try:
            with pdfplumber.open(pdf) as p:
                text = "\n".join(page.extract_text() or "" for page in p.pages)
            for tax_id, label in by_tax_id.items():
                if tax_id in text:
                    return label
        except Exception:
            continue
    return None


def _historical_route_company(trip: dict, history: list[dict]) -> str | None:
    """過去 90 天同 from-to 路線出現 ≥ 3 次且公司一致 → 沿用。"""
    if not trip.get("from_short") or not trip.get("to_short") or not trip.get("trip_date"):
        return None
    cutoff = (dt.date.fromisoformat(trip["trip_date"]) - dt.timedelta(days=90)).isoformat()
    matches = [
        h for h in history
        if h["from_short"] == trip["from_short"]
        and h["to_short"] == trip["to_short"]
        and h["date"] >= cutoff
        and h.get("company")
        and h["company"] != "私人"
    ]
    if len(matches) < 3:
        return None
    companies = {h["company"] for h in matches}
    if len(companies) == 1:
        return companies.pop()
    return None


def suggest_company(
    trip: dict,
    batch: list[dict],
    *,
    default_company: str | None = None,
) -> tuple[str | None, str]:
    """回傳 (suggested_company_label_or_私人, reason_string)。

    None 表示「無法建議，請使用者選」。
    """
    if trip.get("is_refunded"):
        return None, "退款行程，不分配公司"

    cont = _continuation_of(trip, batch)
    if cont:
        return cont["_assigned_company"], f"同日連續行程，沿用上一趟的「{cont['_assigned_company']}」"

    if _is_hsr_or_airport(trip.get("to_short")) or _is_hsr_or_airport(trip.get("from_short")):
        thsr_company = _same_day_thsr_company(trip.get("trip_date"))
        if thsr_company:
            return thsr_company, f"目的地接駁高鐵/機場，同日 thsr 票已標「{thsr_company}」"

    history = _scan_archive(UBER_ARCHIVE)
    historical = _historical_route_company(trip, history)
    if historical:
        return historical, f"過去 90 天同路線多次標為「{historical}」"

    flags = []
    if _is_late_night(trip.get("trip_time_start")):
        flags.append("深夜")
    if _is_weekend(trip.get("trip_date")):
        flags.append("週末")
    if _is_short_trip(trip):
        flags.append("短途")
    if len(flags) >= 2:
        return "私人", f"啟發式判斷可能為私人（{' + '.join(flags)}）"

    if default_company:
        return default_company, f"使用預設公司「{default_company}」"

    return None, "無建議，請使用者選擇"


def annotate_batch(
    trips: list[dict],
    *,
    default_company: str | None = None,
) -> list[dict]:
    """對一批 trip 順序套用啟發式（按時間排序，因為連續行程要看前一趟）。

    產生 _suggested_company 與 _suggestion_reason 兩個欄位。
    使用者確認後呼叫者會把 _assigned_company 設好，下一輪才能正確連動。
    """
    sorted_trips = sorted(
        trips,
        key=lambda t: (t.get("trip_date") or "", t.get("trip_time_start") or ""),
    )
    for trip in sorted_trips:
        suggested, reason = suggest_company(
            trip, sorted_trips, default_company=default_company,
        )
        trip["_suggested_company"] = suggested
        trip["_suggestion_reason"] = reason
    return sorted_trips
