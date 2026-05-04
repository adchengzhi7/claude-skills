#!/usr/bin/env python3
"""台灣高鐵購票證明自動下載

預設走 T Express → 電子車票證明 → 對號座 流程（最常見）。
報帳用：必填 統編 + 公司名稱。

Usage:
    python3 download.py \\
        --pnr 87654321 \\
        --tid 1234567890123 \\
        --date 2026-04-29 \\
        --tax-id 12345678 \\
        --company "好好谷倉股份有限公司"

統編可從環境變數讀（避免每次打）：
    export THSR_TAX_ID=12345678
    export THSR_COMPANY="好好谷倉股份有限公司"

或從 macOS Keychain：
    security add-generic-password -a "$USER" -s "thsr-tax-id" -w "12345678"
    security add-generic-password -a "$USER" -s "thsr-company" -w "好好谷倉股份有限公司"
"""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError:
    print("❌ 缺少 playwright。請先執行：")
    print("   pip3 install --break-system-packages playwright")
    print("   python3 -m playwright install chromium")
    sys.exit(1)

QUERY_URL = "https://ptis.thsrc.com.tw/ptis/"
OUTPUT_DIR = Path.home() / "Downloads" / "thsr_receipts"
DEBUG_DIR = Path("/tmp/thsr-debug")
COMPANIES_PATH = Path.home() / ".config" / "thsr-receipt" / "companies.json"


def safe_filename(s: str) -> str:
    s = s.strip().replace("/", "-").replace(".", "-")
    return re.sub(r"[\\/:*?\"<>|\s]+", "", s)


def get_keychain(service: str) -> str | None:
    user = os.environ.get("USER", "")
    try:
        r = subprocess.run(
            ["security", "find-generic-password", "-a", user, "-s", service, "-w"],
            capture_output=True, text=True, check=True
        )
        return r.stdout.strip() or None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def load_companies() -> list[dict]:
    """讀 ~/.config/thsr-receipt/companies.json，回傳 [{label, tax_id, name}, ...]。檔案不存在或壞掉就回 []。"""
    import json
    if not COMPANIES_PATH.exists():
        return []
    try:
        data = json.loads(COMPANIES_PATH.read_text(encoding="utf-8"))
        return [c for c in data if isinstance(c, dict) and "tax_id" in c and "name" in c]
    except Exception:
        return []


def find_company_by_label(label: str) -> dict | None:
    for c in load_companies():
        if c.get("label", "").strip().lower() == label.strip().lower():
            return c
    return None


def resolve_tax_id(cli_value: str | None) -> str:
    return (cli_value
            or os.environ.get("THSR_TAX_ID", "").strip()
            or get_keychain("thsr-tax-id")
            or "")


def resolve_company(cli_value: str | None) -> str:
    return (cli_value
            or os.environ.get("THSR_COMPANY", "").strip()
            or get_keychain("thsr-company")
            or "")


def download_receipt(args, headless: bool = True) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)

    date_dashed = args.date.strip()
    date_slashed = date_dashed.replace("-", "/")
    seat_value = "res" if args.seat_type == "reserved" else "free"

    print(f"🚄 高鐵電子車票證明下載")
    print(f"   訂位代號: {args.pnr}")
    print(f"   車票號碼: {args.tid}")
    print(f"   搭乘日期: {date_dashed}")
    print(f"   票種: {'對號座' if seat_value == 'res' else '自由座'}")
    print(f"   統編: {args.tax_id}")
    print(f"   公司名稱: {args.company}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(accept_downloads=True, locale="zh-TW")
        page = context.new_page()

        page.goto(QUERY_URL, wait_until="domcontentloaded", timeout=30000)

        # 1. 主 tab → T Express
        page.locator('a:visible:has-text("T Express")').first.click()
        page.wait_for_load_state("networkidle", timeout=10000)

        # 2. sub-tab → 電子車票證明
        page.locator('a:visible:has-text("電子車票證明")').first.click()
        page.wait_for_load_state("networkidle", timeout=10000)

        # 3. 選對號座 / 自由座 → 觸發欄位顯示
        page.locator('select#carClassTypeProof').first.select_option(value=seat_value)
        page.wait_for_timeout(1500)

        # 4. 填表 — 電子車票證明 sub-tab 的欄位 id 是 txProofPnr / 等
        # 注意：頁面上同時存在「一般查詢列印」與「電子車票證明」兩組 input[name="pnr"]，
        # 一般查詢的 id=txPnr，電子證明的 id=txProofPnr，必須鎖 txProofPnr 才會在當前 sub-tab。
        page.locator('input#txProofPnr').first.fill(args.pnr)
        # tid 沒有 id，用 visible 限定 + 在 carClassTypeProof 同一個 form 範圍內
        page.locator('input[name="tid"]:visible').first.fill(args.tid)
        # goTravelDate 是 readonly 的 datepicker，先脫掉 readonly 再填，並 dispatch change 觸發驗證
        date_input = page.locator('input#goTravelDate:visible').first
        date_input.evaluate("el => el.removeAttribute('readonly')")
        date_input.fill(date_slashed)
        date_input.dispatch_event('change')

        page.screenshot(path=str(DEBUG_DIR / "01-form-filled.png"), full_page=True)

        # 5. 開始查詢
        page.locator('button:visible:has-text("開始查詢")').first.click()
        page.wait_for_load_state("networkidle", timeout=20000)
        page.screenshot(path=str(DEBUG_DIR / "02-after-query.png"), full_page=True)
        (DEBUG_DIR / "02-after-query.html").write_text(page.content())

        # 5b. 偵測「請確認票卡資料正確性」錯誤 modal —
        #    HSR 對「資料找不到 / 已下載過 / 票異常」用同一個提示
        for err_text in ["請確認票卡資料正確性", "查無資料", "已下載"]:
            try:
                if page.locator(f'text="{err_text}"').first.is_visible(timeout=1500):
                    raise RuntimeError(
                        f"高鐵回應「{err_text}」。最常見原因：\n"
                        f"  1. 這張票之前在 T Express App 已經點過「下載電子車票證明」（每張一輩子只能 1 次）\n"
                        f"  2. 訂位代號 / 車票號碼 / 搭乘日期 與實際不符\n"
                        f"  3. 還沒到可下載期間（乘車日 + 2 日起才開放）"
                    )
            except PWTimeout:
                continue

        # 6. 結果頁：填統編 + 公司名稱
        # 多種可能 selector，選擇先出現且 visible 的那個
        tax_filled = False
        for sel in [
            'input[placeholder="統一編號"]',
            'input[placeholder*="統一編號"]',
            'input[name*="taxId" i]',
            'input[name*="vatNo" i]',
        ]:
            try:
                el = page.locator(sel).first
                if el.is_visible(timeout=2000):
                    el.fill(args.tax_id)
                    tax_filled = True
                    break
            except Exception:
                continue
        if not tax_filled:
            raise RuntimeError("找不到統一編號欄位，可能網頁結構改了。截圖看 /tmp/thsr-debug/02-after-query.png")

        company_filled = False
        for sel in [
            'input[placeholder*="營利事業名稱"]',
            'input[placeholder*="營業人"]',
            'input[name*="companyName" i]',
            'input[name*="vatTitle" i]',
        ]:
            try:
                el = page.locator(sel).first
                if el.is_visible(timeout=2000):
                    el.fill(args.company)
                    company_filled = True
                    break
            except Exception:
                continue
        if not company_filled:
            print("⚠️ 找不到公司名稱欄位，繼續嘗試（可能個人申請也可以）")

        page.screenshot(path=str(DEBUG_DIR / "03-tax-filled.png"), full_page=True)

        # 7. 找下載 / 列印按鈕
        download_clicked = False
        with page.expect_download(timeout=30000) as dl_info:
            for sel in [
                'button:visible:has-text("下載電子車票證明")',
                'a:visible:has-text("下載電子車票證明")',
                'button:visible:has-text("下載")',
                'a:visible:has-text("下載")',
                'button:visible:has-text("列印")',
                'button:visible:has-text("確認")',
            ]:
                try:
                    el = page.locator(sel).first
                    if el.is_visible(timeout=2000):
                        el.click()
                        download_clicked = True
                        break
                except Exception:
                    continue
            if not download_clicked:
                raise RuntimeError("找不到下載 / 列印按鈕。截圖 /tmp/thsr-debug/03-tax-filled.png")

        download = dl_info.value

        parts = [
            safe_filename(date_dashed),
            safe_filename(args.from_st) if args.from_st else "",
            safe_filename(args.to_st) if args.to_st else "",
            safe_filename(args.pnr),
        ]
        parts = [p for p in parts if p]
        save_path = OUTPUT_DIR / ("-".join(parts) + ".pdf")
        download.save_as(save_path)

        page.screenshot(path=str(DEBUG_DIR / "04-after-download.png"), full_page=True)
        browser.close()
        return save_path


def main():
    parser = argparse.ArgumentParser(description="台灣高鐵電子車票證明下載（T Express 流程）")
    parser.add_argument("--pnr", help="訂位代號（8 碼數字）")
    parser.add_argument("--tid", help="車票號碼（13 碼數字，多張票任選一張）")
    parser.add_argument("--date", help="搭乘日期 YYYY-MM-DD")
    parser.add_argument("--from", dest="from_st", default="", help="起站（中文，僅用於檔名）")
    parser.add_argument("--to", dest="to_st", default="", help="迄站（中文，僅用於檔名）")
    parser.add_argument("--seat-type", choices=["reserved", "free"], default="reserved",
                        help="對號座 reserved（預設）/ 自由座 free")
    parser.add_argument("--tax-id", default=None, help="統一編號（8 碼）。優先序：CLI > --company-label > companies.json 單筆 > env THSR_TAX_ID > Keychain")
    parser.add_argument("--company", default=None, help="營利事業名稱（同上優先序）")
    parser.add_argument("--company-label", default=None, help="從 ~/.config/thsr-receipt/companies.json 挑公司（用 label 比對）")
    parser.add_argument("--list", dest="list_companies", action="store_true", help="列出 ~/.config/thsr-receipt/companies.json 裡所有公司，然後離開")
    args = parser.parse_args()

    # --list: print and exit
    if args.list_companies:
        companies = load_companies()
        if not companies:
            print(f"📭 {COMPANIES_PATH} 不存在或沒有公司。")
            print(f"   範本格式：")
            print('   [{"label": "好好谷倉", "tax_id": "12345678", "name": "好好谷倉股份有限公司"}]')
            return
        print(f"📋 {COMPANIES_PATH} ({len(companies)} 筆):")
        for c in companies:
            label = c.get("label", "(無 label)")
            print(f"   • {label}  [統編 {c['tax_id']}]  {c['name']}")
        return

    # 一般下載流程：pnr / tid / date 必填
    missing = [name for name, val in (("--pnr", args.pnr), ("--tid", args.tid), ("--date", args.date)) if not val]
    if missing:
        parser.error(f"缺少必要參數：{', '.join(missing)}（用 --list 看可用公司）")

    if not re.fullmatch(r"\d{8}", args.pnr):
        print(f"⚠️ 訂位代號預期 8 碼數字，收到 {args.pnr!r}（仍嘗試）")
    if not re.fullmatch(r"\d{13}", args.tid):
        print(f"⚠️ 車票號碼預期 13 碼數字，收到 {args.tid!r}（仍嘗試）")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date.strip()):
        print(f"❌ 日期格式應為 YYYY-MM-DD，收到 {args.date!r}")
        sys.exit(1)

    # 解析公司：優先 CLI 直給，其次 --company-label 查表，再來 fallback chain
    if args.company_label:
        match = find_company_by_label(args.company_label)
        if not match:
            print(f"❌ 在 {COMPANIES_PATH} 找不到 label={args.company_label!r}。用 --list 看可用公司。")
            sys.exit(1)
        args.tax_id = args.tax_id or match["tax_id"]
        args.company = args.company or match["name"]

    # 沒給 CLI / label，看 companies.json 是否只有一筆
    if not args.tax_id and not args.company:
        companies = load_companies()
        if len(companies) == 1:
            args.tax_id = companies[0]["tax_id"]
            args.company = companies[0]["name"]
            print(f"ℹ️ 使用 companies.json 唯一一筆：{companies[0].get('label', companies[0]['name'])}")
        elif len(companies) > 1:
            print(f"⚠️ companies.json 有 {len(companies)} 筆，請用 --company-label 指定其中一個（或用 --list 看清單）。")
            sys.exit(1)

    args.tax_id = resolve_tax_id(args.tax_id)
    args.company = resolve_company(args.company)
    if not args.tax_id:
        print("❌ 沒提供統一編號。可選：")
        print("   --tax-id 12345678 --company \"XX 股份有限公司\"")
        print("   --company-label \"好好谷倉\"（前提：~/.config/thsr-receipt/companies.json 已建立）")
        print("   env THSR_TAX_ID + THSR_COMPANY")
        print("   Keychain thsr-tax-id + thsr-company")
        sys.exit(1)
    if not re.fullmatch(r"\d{8}", args.tax_id):
        print(f"❌ 統編應為 8 碼數字，收到 {args.tax_id!r}")
        sys.exit(1)

    headed_env = os.environ.get("THSR_HEADED", "").strip().lower()
    headless = headed_env not in ("1", "true", "yes")

    try:
        path = download_receipt(args, headless=headless)
    except Exception as e:
        print(f"❌ 下載失敗：{e}")
        print("📁 除錯快照：/tmp/thsr-debug/")
        if headless:
            print("👉 用 headed 模式重試：")
            print(f"   THSR_HEADED=1 python3 {sys.argv[0]} --pnr {args.pnr} --tid {args.tid} --date {args.date}")
        sys.exit(1)

    pwd = args.date.replace("-", "")
    print(f"\n✅ 已儲存：{path}")
    print(f"🔑 PDF 密碼：{pwd}（高鐵規定 = 乘車日 YYYYMMDD）")
    try:
        subprocess.run(["open", "-R", str(path)], check=False)
    except Exception:
        pass


if __name__ == "__main__":
    main()
