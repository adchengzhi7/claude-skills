"""uber-receipt CLI 入口。

模式：
    --list                    列出 companies.json 內容
    --inspect PDF             解析單一 PDF（不歸檔），印 JSON
    --single PDF              歸檔單一 PDF（用 --company-label 或 --personal）
    --batch PATH              掃 PATH 內所有 receipt_*.pdf，互動式分配
    --report YYYY-MM          重新產生指定月份 summary

主要互動模式（--batch）：
    Claude 會用 Skill 引導使用者每張 PDF 的分配，最終呼叫
    --single 或 internal API 完成歸檔。

直接給人用的 happy path（單檔）：
    python3 main.py --single ~/Downloads/receipt_xxx.pdf --company-label 我的公司
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from classify import annotate_batch  # noqa: E402
from companies import get_company, list_summary, load_companies  # noqa: E402
from organize import organize  # noqa: E402
from parse import parse_pdf  # noqa: E402
from report import generate_report  # noqa: E402
from gmail_fetcher import fetch_trips, get_credentials, setup_instructions  # noqa: E402


def _resolve_company(args) -> str | None:
    if args.personal:
        return "私人"
    if args.company_label:
        c = get_company(args.company_label)
        if not c:
            labels = ", ".join(c["label"] for c in load_companies())
            print(f"❌ 找不到公司 label '{args.company_label}'。可用：{labels}", file=sys.stderr)
            sys.exit(1)
        return c["label"]
    return None


def cmd_list():
    print(list_summary())


def cmd_inspect(pdf_path: str):
    result = parse_pdf(pdf_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_single(args):
    trip = parse_pdf(args.pdf)
    if trip.get("is_eats"):
        print(f"❌ {trip['error']}", file=sys.stderr)
        sys.exit(1)

    company = _resolve_company(args)

    print("📄 解析結果：")
    print(f"   日期: {trip.get('trip_date')} {trip.get('trip_time_start') or ''}-{trip.get('trip_time_end') or ''}")
    print(f"   路線: {trip.get('from_short')} → {trip.get('to_short')}")
    print(f"   金額: NT$ {trip.get('total')}（行程 {trip.get('trip_fare')} + 處理費 {trip.get('processing_fee')}）")
    print(f"   車輛: {trip.get('product')} {trip.get('vehicle_plate')} / {trip.get('fleet')}")
    if trip.get("is_taxi"):
        print(f"   ⚠️ 計程車行程（駕駛執業登記證 {trip.get('driver_license')}），車資無發票，僅處理費 {trip.get('processing_fee')} 可改統編")
    if trip.get("is_refunded"):
        print("   🔻 退款行程，將歸到 _refunded/")

    result = organize(trip, company, move=not args.copy, overwrite=args.overwrite)

    if result["action"] == "skipped":
        print(f"⏭ 略過：{result['target']}（{result.get('reason')}）")
        return
    print(f"✅ 已{result['action']}：{result['target']}")


def cmd_batch(args):
    """批次模式 — 解析 + 加 suggestion，輸出 JSON 給 Claude 處理互動分配。

    這個指令不直接做互動，因為互動邏輯在 SKILL.md 裡（Claude 主導）。
    它只負責：批次掃描 → 解析 → 套用啟發式 → 印出可讀結構。
    """
    folder = Path(args.path).expanduser().resolve()
    if not folder.exists():
        print(f"❌ 路徑不存在: {folder}", file=sys.stderr)
        sys.exit(1)

    pdfs = sorted(folder.glob("receipt_*.pdf")) if folder.is_dir() else [folder]
    if not pdfs:
        print(f"⚠️ {folder} 內沒有 receipt_*.pdf", file=sys.stderr)
        sys.exit(1)

    trips = []
    for pdf in pdfs:
        try:
            trip = parse_pdf(pdf)
            if trip.get("is_eats"):
                continue
            trips.append(trip)
        except Exception as e:
            print(f"⚠️ 解析失敗 {pdf.name}: {e}", file=sys.stderr)

    default_company = args.default_company or None
    annotated = annotate_batch(trips, default_company=default_company)

    if args.json:
        print(json.dumps(annotated, ensure_ascii=False, indent=2, default=str))
        return

    print(f"📦 掃到 {len(annotated)} 張 PDF\n")
    print(f"{'#':<3} {'日期':<11} {'時間':<6} {'路線':<22} {'金額':<8} 建議")
    print("-" * 80)
    for i, t in enumerate(annotated, 1):
        route = f"{t.get('from_short') or '?'} → {t.get('to_short') or '?'}"
        amount = f"${t.get('total')}" if t.get("total") else "?"
        suggested = t.get("_suggested_company") or "—"
        print(f"{i:<3} {t.get('trip_date') or '?':<11} {t.get('trip_time_start') or '?':<6} {route:<22} {amount:<8} {suggested}  ({t.get('_suggestion_reason')})")


def cmd_from_gmail(args):
    """從 Gmail 抓 Uber 行程信 → 解析 email → 用 Uber 登入 session 下載官方 PDF + 統一發票 XML → 從 XML 反查公司 → 建議分配。"""
    import datetime as _dt

    sys.path.insert(0, str(Path(__file__).parent))
    from email_parser import parse_xml_invoice  # noqa
    from uber_browser import enrich_and_download, is_logged_in_quick, PROFILE_DIR  # noqa

    if not get_credentials():
        print(setup_instructions(), file=sys.stderr)
        sys.exit(1)

    since = None
    if args.since:
        since = _dt.datetime.fromisoformat(args.since)
    else:
        since = _dt.datetime.now() - _dt.timedelta(days=60)

    target = Path(args.target).expanduser().resolve() if args.target else None

    try:
        results = fetch_trips(since=since, target_dir=target, skip_processed=not args.refetch)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    parsed = [r for r in results if r["status"] == "parsed"]
    skipped = [r for r in results if r["status"] == "skipped_processed"]
    failed = [r for r in results if r["status"] == "parse_failed"]

    print(f"📦 IMAP {len(results)} 封 → 解析 {len(parsed)} / 已處理略過 {len(skipped)} / 解析失敗 {len(failed)}")

    if not parsed:
        return

    trips = parsed

    # 第二階段：用 Uber 登入 session 抓官方 PDF + 統一發票
    if not args.skip_browser_download and PROFILE_DIR.exists() and is_logged_in_quick():
        # 用第一張的 source_path 推斷 target_dir（gmail_fetcher 已建好的）
        first_eml = next((Path(t["source_path"]) for t in trips if t.get("source_path")), None)
        download_dir = first_eml.parent if first_eml else (target or Path("/tmp"))

        print(f"\n🌐 Uber 已登入 → 下載官方 PDF + 統一發票到 {download_dir}")
        enrich_and_download(trips, download_dir, headless=True)

        # 對每張 trip，找 .xml invoice → 抽買方統編 → 反查公司
        company_lookup = {c["tax_id"]: c["label"] for c in load_companies()}
        for t in trips:
            for inv in t.get("_invoices", []):
                if inv.get("ext") == ".xml" and inv.get("path"):
                    try:
                        meta = parse_xml_invoice(inv["path"])
                        t["_invoice_meta"] = meta
                        if meta.get("buyer_id") in company_lookup:
                            t["_xml_company"] = company_lookup[meta["buyer_id"]]
                            break
                    except Exception as e:
                        print(f"   ⚠️ 解析 XML 失敗 {inv['path']}: {e}", file=sys.stderr)
    elif not args.skip_browser_download:
        print("\n⚠️ Uber 未登入，跳過官方 PDF 下載 — 跑 uber_browser.py --setup 設定後可全自動")

    # 啟發式建議；若 XML 已給公司就覆蓋（最準）
    annotated = annotate_batch(trips, default_company=args.default_company or None)
    for t in annotated:
        if t.get("_xml_company"):
            t["_suggested_company"] = t["_xml_company"]
            inv_no = t.get("_invoice_meta", {}).get("invoice_number") or "?"
            t["_suggestion_reason"] = f"XML 統一發票買方 → 「{t['_xml_company']}」（發票號 {inv_no}）"

    if args.json:
        print(json.dumps(annotated, ensure_ascii=False, indent=2, default=str))
        return

    print(f"\n📋 抓到 {len(annotated)} 張可處理的 Uber PDF：\n")
    print(f"{'#':<3} {'日期':<11} {'時間':<6} {'路線':<22} {'金額':<8} 建議")
    print("-" * 80)
    for i, t in enumerate(annotated, 1):
        route = f"{t.get('from_short') or '?'} → {t.get('to_short') or '?'}"
        amount = f"${t.get('total')}" if t.get("total") else "?"
        suggested = t.get("_suggested_company") or "—"
        print(f"{i:<3} {t.get('trip_date') or '?':<11} {t.get('trip_time_start') or '?':<6} {route:<22} {amount:<8} {suggested}  ({t.get('_suggestion_reason')})")


def cmd_report(month: str):
    result = generate_report(month)
    if "error" in result:
        print(f"❌ {result['error']}", file=sys.stderr)
        sys.exit(1)
    print(f"✅ {result['month']} 報表已產生：{result['trip_count']} 趟 / NT$ {result['total']:,}")
    print(f"   📊 {result['csv_path']}")
    print(f"   📝 {result['md_path']}")


def build_parser():
    p = argparse.ArgumentParser(
        prog="uber-receipt",
        description="Uber 收據 PDF 整理 + 報帳工具",
    )
    p.add_argument("--list", action="store_true", help="列出公司清單")
    p.add_argument("--inspect", metavar="PDF", help="解析單一 PDF（不動檔案，印 JSON）")
    p.add_argument("--single", dest="pdf", metavar="PDF", help="歸檔單一 PDF")
    p.add_argument("--batch", dest="path", metavar="PATH", help="批次掃描資料夾（印建議表給 Claude 處理）")
    p.add_argument("--report", metavar="YYYY-MM", help="產生月份 summary.csv + summary.md")

    p.add_argument("--company-label", help="（搭配 --single）指定公司 label")
    p.add_argument("--personal", action="store_true", help="（搭配 --single）標記為私人行程")
    p.add_argument("--copy", action="store_true", help="複製而不是移動原檔")
    p.add_argument("--overwrite", action="store_true", help="若目標檔已存在，強制覆蓋")
    p.add_argument("--default-company", help="（搭配 --batch / --from-gmail）批次預設公司")
    p.add_argument("--json", action="store_true", help="（搭配 --batch / --from-gmail）以 JSON 輸出")

    p.add_argument("--wizard", action="store_true", help="🪄 新手 setup 引導（5 步走完，~5 分鐘）")
    p.add_argument("--from-gmail", action="store_true", help="從 Gmail IMAP 抓 Uber 收據（需先設 App Password）")
    p.add_argument("--since", metavar="YYYY-MM-DD", help="（搭配 --from-gmail）只抓這個日期之後的信件，預設 60 天")
    p.add_argument("--target", help="（搭配 --from-gmail）暫存資料夾")
    p.add_argument("--refetch", action="store_true", help="（搭配 --from-gmail）略過已處理紀錄，重抓全部")
    p.add_argument("--skip-browser-download", action="store_true", help="（搭配 --from-gmail）跳過 Uber 登入 session 下載官方 PDF + 統一發票")
    return p


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.wizard:
        from wizard import run as run_wizard
        run_wizard()
    elif args.list:
        cmd_list()
    elif args.inspect:
        cmd_inspect(args.inspect)
    elif args.pdf:
        cmd_single(args)
    elif args.path:
        cmd_batch(args)
    elif args.report:
        cmd_report(args.report)
    elif getattr(args, "from_gmail", False):
        cmd_from_gmail(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
