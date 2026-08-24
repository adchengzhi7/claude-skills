#!/usr/bin/env python3
"""台鐵購票證明自動下載

Usage:
    python3 download.py <訂票代碼>

需要：
- Playwright (pip3 install playwright && playwright install chromium)
- macOS Keychain 中存好身分證字號：
    security add-generic-password -a "$USER" -s "tra-id" -w "你的身分證字號"
"""
import os
import re
import sys
import subprocess
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError:
    print("❌ 缺少 playwright。請先執行：")
    print("   pip3 install --break-system-packages playwright")
    print("   python3 -m playwright install chromium")
    sys.exit(1)

QUERY_URL = "https://www.railway.gov.tw/tra-tip-web/tip/tip001/tip115/query"
OUTPUT_DIR = Path.home() / "Downloads" / "tra_receipts"


def get_id_from_keychain() -> str:
    """從 macOS Keychain 讀身分證字號。"""
    user = os.environ.get("USER", "")
    if env_id := os.environ.get("TRA_ID"):
        return env_id.strip()
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-a", user, "-s", "tra-id", "-w"],
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ Keychain 沒找到 tra-id。請執行：")
        print(f'   security add-generic-password -a "{user}" -s "tra-id" -w "你的身分證字號"')
        print("   （或設定環境變數 TRA_ID=你的身分證字號）")
        sys.exit(1)


def safe_filename(s: str) -> str:
    s = s.strip().replace("/", "-").replace(".", "-")
    s = re.sub(r"[\\/:*?\"<>|\s]+", "", s)
    return s


def download_receipt(booking_code: str, id_number: str, headless: bool = True) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(accept_downloads=True, locale="zh-TW")
        page = context.new_page()

        page.goto(QUERY_URL, wait_until="domcontentloaded", timeout=30000)

        # 切到「身分證字號」or「護照號碼/統一證號」radio
        # 台灣身分證: [A-Z][12]\d{8}（第 2 碼是 1/2）
        # 居留證統一證號 / 護照: 其他格式 → 走 PASSPORT_NO
        id_type_override = os.environ.get("TRA_ID_TYPE", "").strip().upper()
        if id_type_override in ("PERSON_ID", "PASSPORT_NO"):
            id_type = id_type_override
        elif re.fullmatch(r"[A-Z][12]\d{8}", id_number):
            id_type = "PERSON_ID"
        else:
            id_type = "PASSPORT_NO"
        print(f"   ID 類型：{id_type}")
        try:
            radio_id = "personlType" if id_type == "PERSON_ID" else "passport"
            page.locator(f'label[for="{radio_id}"]').first.click(timeout=3000)
        except Exception as e:
            print(f"   ⚠️ 切 ID 類型 radio 失敗：{e}")

        id_filled = False
        for sel in [
            'input[name="pid"]',
            'input[name="idNumber"]',
            'input[placeholder*="身分證"]',
            'input[id*="pid" i]',
        ]:
            try:
                if page.locator(sel).first.is_visible(timeout=1000):
                    page.locator(sel).first.fill(id_number)
                    id_filled = True
                    break
            except Exception:
                continue

        code_filled = False
        for sel in [
            'input[name="recNo"]',
            'input[name="orderCode"]',
            'input[name="bookingCode"]',
            'input[placeholder*="訂票代碼"]',
            'input[id*="orderCode" i]',
            'input[id*="recNo" i]',
        ]:
            try:
                if page.locator(sel).first.is_visible(timeout=1000):
                    page.locator(sel).first.fill(booking_code)
                    code_filled = True
                    break
            except Exception:
                continue

        if not (id_filled and code_filled):
            inputs = page.locator('input[type="text"]:visible, input:not([type]):visible')
            if inputs.count() >= 2:
                inputs.nth(0).fill(id_number)
                inputs.nth(1).fill(booking_code)
            else:
                raise RuntimeError("找不到表單欄位，可能網頁結構改了，請以 headed 模式檢查")

        for sel in [
            'button[type="submit"]:has-text("查詢")',
            'button[type="submit"]',
            'input[type="submit"][value*="查詢"]',
            'button:visible:has-text("查詢"):not([disabled])',
        ]:
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=1000):
                    btn.click()
                    break
            except Exception:
                continue

        page.wait_for_load_state("networkidle", timeout=15000)

        try:
            page.locator(f'a:has-text("{booking_code}")').first.click(timeout=5000)
            page.wait_for_load_state("networkidle", timeout=15000)
        except PWTimeout:
            pass

        download_clicked = False
        with page.expect_download(timeout=15000) as dl_info:
            for sel in [
                'a:has-text("下載購票證明")',
                'button:has-text("下載購票證明")',
                'a:has-text("購票證明")',
                'button:has-text("購票證明")',
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
                raise RuntimeError("找不到「下載購票證明」按鈕")
        download = dl_info.value

        # 先存到 temp，再從 PDF 內容抽 metadata 重新命名
        tmp_path = OUTPUT_DIR / f".tmp-{booking_code}.pdf"
        download.save_as(tmp_path)
        browser.close()

        meta = extract_metadata_from_pdf(tmp_path)
        ride_date = meta.get("ride_date") or "unknown-date"
        parts = [safe_filename(ride_date)]
        if meta.get("from_st"):
            parts.append(safe_filename(meta["from_st"]))
        if meta.get("to_st"):
            parts.append(safe_filename(meta["to_st"]))
        # 優先用票號（每張票唯一，方便對帳），抓不到 fallback 用訂票代碼
        parts.append(safe_filename(meta.get("ticket_no") or booking_code))

        # 依乘車日期 YYYY-MM 分資料夾（方便月報帳）
        year_month = ride_date[:7] if len(ride_date) >= 7 else "unknown"
        target_dir = OUTPUT_DIR / year_month
        target_dir.mkdir(parents=True, exist_ok=True)
        save_path = target_dir / ("-".join(parts) + ".pdf")
        tmp_path.rename(save_path)
        return save_path


def extract_metadata_from_pdf(pdf_path: Path) -> dict:
    """從台鐵購票證明 PDF 抽票號 / 乘車日 / 起站 / 訖站。"""
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), "-"],
            capture_output=True, text=True, check=True
        )
        text = result.stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {}

    meta = {}
    # 票號: 1 英文 + 數字（如 N60149229164197），位於「票號」字樣後
    if m := re.search(r"票號\s+([A-Z]\d{8,})", text):
        meta["ticket_no"] = m.group(1)
    # 乘車日格式: 2026/04/27
    if m := re.search(r"(20\d{2}/\d{2}/\d{2})\s+\d{2}:\d{2}\s+(\S+)\s*>\s*\d{2}:\d{2}\s+(\S+)", text):
        meta["ride_date"] = m.group(1).replace("/", "-")
        meta["from_st"] = m.group(2)
        meta["to_st"] = m.group(3)
    return meta


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 download.py <訂票代碼>")
        sys.exit(1)

    booking_code = sys.argv[1].strip()
    if not re.fullmatch(r"\d{6,9}", booking_code):
        print(f"⚠️  訂票代碼看起來怪怪的：{booking_code}（預期 6-9 位數字）")

    id_number = get_id_from_keychain()

    headed_env = os.environ.get("TRA_HEADED", "").strip().lower()
    headless = headed_env not in ("1", "true", "yes")

    print(f"🚆 下載訂票代碼 {booking_code} 的購票證明（headless={headless}）...")
    try:
        path = download_receipt(booking_code, id_number, headless=headless)
    except Exception as e:
        print(f"❌ 下載失敗：{e}")
        print(f"📁 除錯快照：/tmp/tra-debug/")
        if headless:
            print("👉 用 headed 模式重試（看得到瀏覽器、可手動補驗證碼）：")
            print(f"   TRA_HEADED=1 python3 {sys.argv[0]} {booking_code}")
        sys.exit(1)

    print(f"✅ 已儲存：{path}")
    try:
        subprocess.run(["open", "-R", str(path)], check=False)
    except Exception:
        pass


if __name__ == "__main__":
    main()
