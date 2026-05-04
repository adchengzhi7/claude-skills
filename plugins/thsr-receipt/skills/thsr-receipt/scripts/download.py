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
import shutil
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

# 高鐵 12 站中英文 label（依 HSR 網站 select option 文字）
HSR_STATIONS = {
    "南港": "南港 (Nangang)",
    "台北": "台北 (Taipei)",
    "板橋": "板橋 (Banqiao)",
    "桃園": "桃園 (Taoyuan)",
    "新竹": "新竹 (Hsinchu)",
    "苗栗": "苗栗 (Miaoli)",
    "台中": "台中 (Taichung)",
    "彰化": "彰化 (Changhua)",
    "雲林": "雲林 (Yunlin)",
    "嘉義": "嘉義 (Chiayi)",
    "台南": "台南 (Tainan)",
    "左營": "左營 (Zuoying)",
}
# 常見繁體別名 → 標準
HSR_STATION_ALIASES = {"臺北": "台北", "臺中": "台中", "臺南": "台南"}


def hsr_station_label(name: str) -> str:
    name = HSR_STATION_ALIASES.get(name.strip(), name.strip())
    if name not in HSR_STATIONS:
        raise ValueError(
            f"不認得高鐵站 {name!r}。合法清單：{', '.join(HSR_STATIONS.keys())}"
        )
    return HSR_STATIONS[name]


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

    date_dashed = args.date.strip()  # HSR 要的格式就是 YYYY-MM-DD（dash 不是 slash）
    seat_value = "res" if args.seat_type == "reserved" else "free"

    print(f"🚄 高鐵電子車票證明下載")
    print(f"   票種類型: {args.ticket_type}")
    if args.ticket_type == "texpress" and args.pnr:
        print(f"   訂位代號: {args.pnr}")
    print(f"   車票號碼: {args.tid}")
    print(f"   搭乘日期: {date_dashed}")
    print(f"   座位: {'對號座' if seat_value == 'res' else '自由座'}")
    if args.from_st: print(f"   起站: {args.from_st}")
    if args.to_st: print(f"   訖站: {args.to_st}")
    print(f"   統編: {args.tax_id}")
    print(f"   公司名稱: {args.company}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(accept_downloads=True, locale="zh-TW")
        page = context.new_page()

        page.goto(QUERY_URL, wait_until="domcontentloaded", timeout=30000)

        if args.ticket_type == "magnetic":
            # 磁票/QR Code 紙票 是預設第一個 tab，不用切
            # 表單欄位：depDate + depStation + arrStation + ticketType + tix
            if not args.from_st or not args.to_st:
                raise RuntimeError("磁票/紙票必須提供 --from 與 --to 站名")

            date_input = page.locator('input#depDate').first
            date_input.evaluate("el => el.removeAttribute('readonly')")
            date_input.fill(date_dashed)
            date_input.dispatch_event('change')

            # 起訖站 — 用完整中英 label 比對 (e.g., "南港 (Nangang)")
            page.locator('select#depStation').first.select_option(
                label=hsr_station_label(args.from_st)
            )
            page.locator('select#arrStation').first.select_option(
                label=hsr_station_label(args.to_st)
            )
            # 自由座只能用車票號碼；對號座也選車票號碼（user 給的是 tid）
            page.locator('select#ticketType').first.select_option(label="車票號碼")
            page.locator('input#tix').first.fill(args.tid)
        else:
            # T Express path: 主 tab 切 T Express → sub-tab 切電子車票證明
            page.locator('a:visible:has-text("T Express")').first.click()
            page.wait_for_load_state("networkidle", timeout=10000)
            page.locator('a:visible:has-text("電子車票證明")').first.click()
            page.wait_for_load_state("networkidle", timeout=10000)

            # 選對號座 / 自由座 → 觸發欄位顯示
            page.locator('select#carClassTypeProof').first.select_option(value=seat_value)
            page.wait_for_timeout(1500)

            # 表單欄位 — 對號座 / 自由座不一樣
            if seat_value == "res":
                if not args.pnr:
                    raise RuntimeError("T Express 對號座必須提供 --pnr 訂位代號")
                page.locator('input#txProofPnr').first.fill(args.pnr)
                page.locator('input[name="tid"]:visible').first.fill(args.tid)
                date_input = page.locator('input#goTravelDate:visible').first
            else:
                page.locator('input[name="txFreeTid"]:visible').first.fill(args.tid)
                date_input = page.locator('input#txFreeDateProof:visible').first

            date_input.evaluate("el => el.removeAttribute('readonly')")
            date_input.fill(date_dashed)
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

        # 6+7. 結果頁 → 統編 + 公司名稱 → 下載
        # T Express 跟磁票流程不一樣：
        #   T Express: 結果頁有靜態 #iUniNumber/#iBuyer 欄位，先填、再點 download_btn（會跳「僅能下載一次」modal，按 #x2_btn 確認）
        #   磁票:      結果頁無靜態欄位，點 download_btn 後 modal 才彈出含統編+公司名 input，填完按 #x2_btn 觸發下載
        if args.ticket_type == "magnetic":
            # 磁票：onclick 直接呼叫 downloadPDF()，無 modal、無統編欄位
            # HSR 限制：磁票 PDF 是「交易紀錄」，非報稅扣抵憑證，不蓋統編戳章
            download_link = page.locator('a.download_btn:visible').first
            if not download_link.is_visible(timeout=3000):
                raise RuntimeError(
                    "找不到磁票結果頁的下載按鈕。\n"
                    "如果 HSR 顯示「已下載」狀態，可重新查詢一次嘗試（交易紀錄通常可重複下載）。\n"
                    "截圖 /tmp/thsr-debug/02-after-query.png"
                )

            with page.expect_download(timeout=30000) as dl_info:
                download_link.click()
            download = dl_info.value
        else:
            # T Express：靜態頁面填 iUniNumber + iBuyer 後點下載
            try:
                page.locator('input#iUniNumber').first.fill(args.tax_id)
            except Exception as e:
                raise RuntimeError(f"找不到 input#iUniNumber：{e}（截圖 /tmp/thsr-debug/02-after-query.png）")
            page.locator('input#iUniNumber').first.dispatch_event('change')
            page.wait_for_timeout(500)
            # 「統編不符合邏輯」警告 modal（若出現）
            for confirm_btn in ['button#x2_btn', 'button:visible:has-text("繼續")']:
                try:
                    btn = page.locator(confirm_btn).first
                    if btn.is_visible(timeout=1500):
                        btn.click()
                        break
                except Exception:
                    continue
            page.locator('input#iBuyer').first.fill(args.company)
            page.locator('input#iBuyer').first.dispatch_event('change')
            page.wait_for_timeout(500)
            page.screenshot(path=str(DEBUG_DIR / "03-tax-filled.png"), full_page=True)

            # 點對應 tid 的下載按鈕 → 跳「僅能下載一次」確認 modal → 按 #x2_btn
            download_link = page.locator(f'a.download_btn[onclick*="{args.tid}"]').first
            if not download_link.is_visible(timeout=3000):
                raise RuntimeError(
                    f"找不到 tid={args.tid} 的下載按鈕。可能此 tid 不在這個訂位代號裡，"
                    f"或網頁結構改了。截圖 /tmp/thsr-debug/03-tax-filled.png"
                )
            with page.expect_download(timeout=30000) as dl_info:
                download_link.click()
                try:
                    page.locator('button#x2_btn').first.click(timeout=5000)
                except Exception:
                    pass
            download = dl_info.value

        parts = [
            safe_filename(date_dashed),
            safe_filename(args.from_st) if args.from_st else "",
            safe_filename(args.to_st) if args.to_st else "",
            safe_filename(args.tid),  # 用 tid（每張票唯一），避免去回票 / 分票同 pnr 撞檔
        ]
        parts = [p for p in parts if p]

        # 依乘車日期 YYYY-MM 分資料夾（方便月報帳）
        year_month = date_dashed[:7] if len(date_dashed) >= 7 else "unknown"
        target_dir = OUTPUT_DIR / year_month
        target_dir.mkdir(parents=True, exist_ok=True)
        save_path = target_dir / ("-".join(parts) + ".pdf")
        download.save_as(save_path)

        page.screenshot(path=str(DEBUG_DIR / "04-after-download.png"), full_page=True)
        browser.close()

    # 7. 自動用 qpdf 解密（密碼就是乘車日 YYYYMMDD，我們已知）
    pwd = date_dashed.replace("-", "")
    if shutil.which("qpdf"):
        tmp_decrypted = save_path.with_name(save_path.stem + ".decrypted.pdf")
        try:
            subprocess.run(
                ["qpdf", "--decrypt", f"--password={pwd}",
                 str(save_path), str(tmp_decrypted)],
                check=True, capture_output=True
            )
            tmp_decrypted.replace(save_path)
            print(f"🔓 已自動解密（原密碼 {pwd}），檔案可直接打開")
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode() if e.stderr else ""
            print(f"⚠️ 自動解密失敗：{stderr}")
            print(f"🔑 PDF 密碼：{pwd} — 開啟時手動輸入即可")
    else:
        print(f"💡 安裝 qpdf 可自動解密：brew install qpdf")
        print(f"🔑 PDF 密碼：{pwd}")

    return save_path


def main():
    parser = argparse.ArgumentParser(description="台灣高鐵電子車票證明下載（T Express 流程）")
    parser.add_argument("--pnr", help="訂位代號（8 碼數字，自由座可省略）")
    parser.add_argument("--tid", help="車票號碼（13 碼數字，多張票任選一張）")
    parser.add_argument("--date", help="搭乘日期 YYYY-MM-DD")
    parser.add_argument("--from", dest="from_st", default="", help="起站（中文，僅用於檔名）")
    parser.add_argument("--to", dest="to_st", default="", help="迄站（中文，僅用於檔名）")
    parser.add_argument("--seat-type", choices=["reserved", "free"], default="reserved",
                        help="對號座 reserved（預設）/ 自由座 free")
    parser.add_argument("--ticket-type", choices=["texpress", "magnetic"], default="texpress",
                        help="texpress = T Express App 電子票（預設）/ magnetic = 磁票/QR Code 紙票（現場/超商買的）")
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

    # 必填檢查
    required = [("--tid", args.tid), ("--date", args.date)]
    if args.ticket_type == "magnetic":
        # 磁票/紙票：要 from / to 站名（HSR 表單要 select）
        required.append(("--from", args.from_st))
        required.append(("--to", args.to_st))
    elif args.seat_type == "reserved":
        # T Express 對號座要訂位代號
        required.append(("--pnr", args.pnr))
    missing = [name for name, val in required if not val]
    if missing:
        parser.error(f"缺少必要參數：{', '.join(missing)}（用 --list 看可用公司）")

    if args.pnr and not re.fullmatch(r"\d{8}", args.pnr):
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

    print(f"\n✅ 已儲存：{path}")
    try:
        subprocess.run(["open", "-R", str(path)], check=False)
    except Exception:
        pass


if __name__ == "__main__":
    main()
