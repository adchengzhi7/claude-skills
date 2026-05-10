"""掃 ~/Downloads/uber_receipts/YYYY-MM/ 產生報帳 summary。

兩個輸出：
    - summary.csv：給 Excel / 財務系統
    - summary.md ：給人 review

排除：
    - 私人行程（檔名 [私人]）
    - 退款行程（_refunded/ 子目錄）

對每張 PDF 重新 parse 一次，這樣 summary 永遠和檔案內容一致；
不依賴解析快取，避免 stale data。
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from companies import load_companies  # noqa: E402
from organize import ARCHIVE_ROOT  # noqa: E402
from parse import parse_pdf  # noqa: E402


def _company_lookup() -> dict[str, dict]:
    return {c["label"]: c for c in load_companies()}


def _company_from_filename(name: str) -> str | None:
    import re
    m = re.search(r"-\[([^\]]+)\]\.pdf$", name)
    return m.group(1) if m else None


def _gather(month: str) -> list[dict]:
    month_dir = ARCHIVE_ROOT / month
    if not month_dir.exists():
        return []

    rows = []
    for pdf in sorted(month_dir.glob("*.pdf")):
        company = _company_from_filename(pdf.name)
        if company == "私人":
            continue
        try:
            trip = parse_pdf(pdf)
        except Exception as e:
            print(f"⚠️ 解析失敗 {pdf.name}: {e}", file=sys.stderr)
            continue
        trip["_company"] = company
        rows.append(trip)
    return rows


def _format_csv(rows: list[dict], out_path: Path) -> None:
    fields = [
        "trip_date", "trip_time_start", "from_short", "to_short",
        "product", "trip_fare", "processing_fee", "total",
        "vehicle_plate", "fleet", "_company", "source_path",
    ]
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "日期", "時間", "起站", "訖站", "產品",
            "行程費用", "處理費", "總計",
            "車牌", "車隊", "公司", "PDF 路徑",
        ])
        for r in rows:
            writer.writerow([r.get(k, "") if r.get(k) is not None else "" for k in fields])


def _format_md(rows: list[dict], month: str, out_path: Path) -> None:
    by_company: dict[str | None, list[dict]] = defaultdict(list)
    for r in rows:
        by_company[r.get("_company")].append(r)

    lookup = _company_lookup()

    lines = [f"# {month} Uber 報帳明細", ""]

    if not rows:
        lines.append("（本月無可報帳行程）")
        out_path.write_text("\n".join(lines), encoding="utf-8")
        return

    grand_total = sum(r.get("total") or 0 for r in rows)
    lines.append(f"**全部合計：NT$ {grand_total:,}**（{len(rows)} 趟）")
    lines.append("")

    for company in sorted(by_company.keys(), key=lambda x: (x is None, x or "")):
        trips = by_company[company]
        if company:
            info = lookup.get(company)
            tax_id = f"統編 {info['tax_id']}" if info else "未登記統編"
            heading = f"## {company}（{tax_id}）"
            if info:
                heading += f" — {info['name']}"
        else:
            heading = "## 未分類"

        total = sum(t.get("total") or 0 for t in trips)
        lines.append(heading)
        lines.append(f"共 {len(trips)} 趟 / 合計 NT$ {total:,}")
        lines.append("")
        lines.append("| 日期 | 時間 | 路線 | 金額 | 車牌 | 車隊 |")
        lines.append("|---|---|---|---|---|---|")
        for t in sorted(trips, key=lambda x: (x.get("trip_date") or "", x.get("trip_time_start") or "")):
            lines.append(
                f"| {t.get('trip_date') or ''} "
                f"| {t.get('trip_time_start') or ''} "
                f"| {t.get('from_short') or '?'} → {t.get('to_short') or '?'} "
                f"| ${t.get('total') or 0} "
                f"| {t.get('vehicle_plate') or '-'} "
                f"| {t.get('fleet') or '-'} |"
            )
        lines.append("")

    lines.append("---")
    lines.append("> ⚠️ 計程車行程（多元計程車）車資無營業人發票；僅 Uber 處理費部分由 Uber Formosa 開立電子發票（可改統編）。")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def generate_report(month: str) -> dict:
    """產生指定月份的 summary.csv 與 summary.md。

    month 格式: 'YYYY-MM'
    """
    month_dir = ARCHIVE_ROOT / month
    if not month_dir.exists():
        return {"error": f"找不到 {month_dir}", "month": month}

    rows = _gather(month)
    csv_path = month_dir / "summary.csv"
    md_path = month_dir / "summary.md"

    _format_csv(rows, csv_path)
    _format_md(rows, month, md_path)

    return {
        "month": month,
        "trip_count": len(rows),
        "total": sum(r.get("total") or 0 for r in rows),
        "csv_path": str(csv_path),
        "md_path": str(md_path),
    }


def main():
    if len(sys.argv) < 2:
        print("用法: python3 report.py YYYY-MM", file=sys.stderr)
        sys.exit(1)
    result = generate_report(sys.argv[1])
    if "error" in result:
        print(f"❌ {result['error']}", file=sys.stderr)
        sys.exit(1)
    print(f"✅ {result['month']} 報表已產生：{result['trip_count']} 趟 / NT$ {result['total']:,}")
    print(f"   📊 {result['csv_path']}")
    print(f"   📝 {result['md_path']}")


if __name__ == "__main__":
    main()
