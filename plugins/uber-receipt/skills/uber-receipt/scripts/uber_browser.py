"""Uber 官方 PDF 下載 — 用 Playwright 持久化瀏覽器 profile。

設計：
    1. setup_login()：headed Chromium 開 riders.uber.com → 等使用者登入 → 關閉視窗 → profile 留存
    2. download_receipt(trip_uuid, out_path)：headless Chromium 用同 profile 自動下載

Profile 路徑：~/.config/receipts/uber-chrome-profile/
（不同 skill 不要共用 profile，避免互相影響）

PDF 下載策略（依序嘗試）：
    a. 直接 GET https://riders.uber.com/trips/<uuid>/receipt.pdf （帶 session cookie）
    b. 導航到 trip page，找「下載 / Download / receipt」按鈕觸發 download 事件
    c. 都失敗 → 回傳 None，呼叫者 fallback 到 email-render
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

try:
    from playwright.sync_api import (
        sync_playwright,
        TimeoutError as PWTimeout,
    )
except ImportError:
    print("❌ 缺 playwright。請先 pip3 install --break-system-packages playwright && python3 -m playwright install chromium", file=sys.stderr)
    raise

PROFILE_DIR = Path.home() / ".config" / "receipts" / "uber-chrome-profile"
RIDERS_HOME = "https://riders.uber.com/"

# 用真實 Chrome（不是 Playwright 內建 Chromium）— Google OAuth 才不會被擋
# channel="chrome" 會優先使用 /Applications/Google Chrome.app
BROWSER_CHANNEL = "chrome"

# 反 automation 偵測 flags
STEALTH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-features=IsolateOrigins,site-per-process",
]


def _launch_persistent(p, *, headless: bool, accept_downloads: bool = False):
    """統一的 launch_persistent_context wrapper — 優先用真實 Chrome + stealth flags。"""
    kwargs = {
        "user_data_dir": str(PROFILE_DIR),
        "headless": headless,
        "args": STEALTH_ARGS,
        "ignore_default_args": ["--enable-automation"],
        "viewport": {"width": 1280, "height": 900},
    }
    if accept_downloads:
        kwargs["accept_downloads"] = True
    try:
        return p.chromium.launch_persistent_context(channel=BROWSER_CHANNEL, **kwargs)
    except Exception:
        # Chrome 沒裝或啟動失敗 → fallback 到 Playwright Chromium
        return p.chromium.launch_persistent_context(**kwargs)

# Uber 行程明細 PDF — 直接 URL（帶登入 session 即可）
TRIP_PDF_URL = "https://riders.uber.com/trips/{uuid}/receipt?contentType=PDF"


# ---------- Setup mode ----------

def is_logged_in_quick(headless: bool = True) -> bool:
    """快速檢查 profile 內是否有 Uber 登入 session。"""
    if not PROFILE_DIR.exists():
        return False
    with sync_playwright() as p:
        ctx = _launch_persistent(p, headless=headless)
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(RIDERS_HOME, wait_until="domcontentloaded", timeout=20_000)
            page.wait_for_timeout(2000)
            url = page.url
            return "auth.uber.com" not in url and "login" not in url.lower()
        except Exception:
            return False
        finally:
            ctx.close()


def _is_logged_in_url(url: str) -> bool:
    """從 URL 判斷是否已登入：不在 auth.uber.com、不在 login 頁。"""
    if not url:
        return False
    if "auth.uber.com" in url:
        return False
    if "/login" in url.lower():
        return False
    if not url.startswith("https://riders.uber.com"):
        return False
    return True


def setup_login(*, auto_close_seconds: int = 3, max_wait_seconds: int = 600):
    """開 headed 瀏覽器讓使用者登入。

    偵測到登入後（URL 連續 N 秒在 riders.uber.com/ 非 auth 頁面）自動關閉。
    使用者也可以手動關閉。
    """
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    print("🌐 開啟瀏覽器...")
    print("📋 請在瀏覽器內登入 Uber。")
    print(f"   登入完成後 {auto_close_seconds} 秒會自動關閉，不用手動。")

    with sync_playwright() as p:
        ctx = _launch_persistent(p, headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.goto(RIDERS_HOME, wait_until="domcontentloaded", timeout=30_000)
        except Exception as e:
            print(f"⚠️ 開啟首頁失敗：{e}")

        # 偵測登入：URL 連續 N 秒都是「已登入」狀態
        deadline = time.time() + max_wait_seconds
        logged_in_since: float | None = None
        last_url = ""
        while time.time() < deadline:
            if not ctx.pages:
                # 使用者手動關閉視窗
                break
            try:
                url = page.url if page else ""
            except Exception:
                break
            if url != last_url:
                last_url = url
                if _is_logged_in_url(url):
                    print(f"   👀 偵測到已登入頁面：{url}")
                    logged_in_since = time.time()
                else:
                    logged_in_since = None
            elif logged_in_since and time.time() - logged_in_since >= auto_close_seconds:
                print("✨ 登入確認，自動關閉瀏覽器")
                break
            time.sleep(0.5)

        try:
            ctx.close()
        except Exception:
            pass

    if is_logged_in_quick(headless=True):
        print("✅ Uber 登入 session 已儲存。後續可全自動下載收據。")
    else:
        print("⚠️ 沒偵測到登入 session。請重跑 --setup 並完成登入。")


# ---------- Download mode ----------

def _fetch_trip_pdf(ctx, trip_uuid: str) -> bytes | None:
    """直接 GET /trips/<uuid>/receipt?contentType=PDF — 行程明細 PDF（392KB 視覺版）。"""
    url = TRIP_PDF_URL.format(uuid=trip_uuid)
    try:
        resp = ctx.request.get(url, timeout=20_000)
    except Exception:
        return None
    if not resp.ok:
        return None
    body = resp.body()
    return body if body[:4] == b"%PDF" else None


def _fetch_invoices(ctx, trip_uuid: str) -> list[dict]:
    """走 Download Invoice 對話框，抓所有 invoice 的 download URL + 內容。

    回傳 [{label, url, ext, bytes}, ...]。沒 invoice 按鈕回 []。
    """
    invoices: list[dict] = []
    page = ctx.new_page()
    try:
        page.goto(f"https://riders.uber.com/trips/{trip_uuid}",
                  wait_until="networkidle", timeout=30_000)
        page.wait_for_timeout(2500)

        if "auth.uber.com" in page.url:
            return []

        if page.locator('button[aria-label="Download Invoice"]').count() == 0:
            return []

        page.click('button[aria-label="Download Invoice"]', force=True)
        page.wait_for_timeout(2500)

        radios = page.locator('input[name="invoice-selection"]').count()
        if radios == 0:
            href = page.evaluate(
                '() => document.querySelector(\'[role="dialog"] a[aria-label="Download"]\')?.href'
            )
            if href:
                ext = ".xml" if ".xml" in href else ".pdf" if ".pdf" in href else ".bin"
                resp = ctx.request.get(href)
                invoices.append({
                    "label": "Invoice",
                    "url": href,
                    "ext": ext,
                    "bytes": resp.body() if resp.ok else None,
                })
            return invoices

        for i in range(radios):
            label = f"Invoice {i + 1}"
            try:
                page.locator(f'text="{label}"').click(force=True)
                page.wait_for_timeout(1200)
                href = page.evaluate(
                    '() => document.querySelector(\'[role="dialog"] a[aria-label="Download"]\')?.href'
                )
                if not href:
                    continue
                ext = ".xml" if ".xml" in href else ".pdf" if ".pdf" in href else ".bin"
                resp = ctx.request.get(href)
                invoices.append({
                    "label": label,
                    "url": href,
                    "ext": ext,
                    "bytes": resp.body() if resp.ok else None,
                })
            except Exception:
                continue
    finally:
        try:
            page.close()
        except Exception:
            pass

    return invoices


def download_all(
    trip_uuid: str,
    target_dir: Path | str,
    *,
    prefix: str = "",
    headless: bool = True,
) -> dict:
    """下載指定 trip 的全部資料：行程明細 PDF + 統一發票（XML + PDF）。

    target_dir / {prefix}detail.pdf       — 行程明細視覺版（~392KB）
    target_dir / {prefix}Invoice1.xml/pdf — 統一發票（核銷主體）
    target_dir / {prefix}Invoice2.xml/pdf — ...

    回傳 {"detail_pdf": str|None, "invoices": [{label, path, url, ext}, ...]}.
    """
    target_dir = Path(target_dir).expanduser()
    target_dir.mkdir(parents=True, exist_ok=True)
    result: dict = {"detail_pdf": None, "invoices": []}

    if not PROFILE_DIR.exists():
        return result

    with sync_playwright() as p:
        ctx = _launch_persistent(p, headless=headless, accept_downloads=True)
        try:
            pdf_bytes = _fetch_trip_pdf(ctx, trip_uuid)
            if pdf_bytes:
                detail_path = target_dir / f"{prefix}detail.pdf"
                detail_path.write_bytes(pdf_bytes)
                result["detail_pdf"] = str(detail_path)

            for inv in _fetch_invoices(ctx, trip_uuid):
                if inv.get("bytes"):
                    label_safe = inv["label"].replace(" ", "")
                    inv_path = target_dir / f"{prefix}{label_safe}{inv['ext']}"
                    inv_path.write_bytes(inv["bytes"])
                    inv["path"] = str(inv_path)
                    inv.pop("bytes", None)
                    result["invoices"].append(inv)
        finally:
            try:
                ctx.close()
            except Exception:
                pass
    return result


def download_receipt(trip_uuid: str, out_path: Path | str, *, headless: bool = True) -> bool:
    """單檔行程明細 PDF 下載（舊 API 相容）。"""
    out_path = Path(out_path).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not PROFILE_DIR.exists():
        return False

    with sync_playwright() as p:
        ctx = _launch_persistent(p, headless=headless, accept_downloads=True)
        try:
            pdf = _fetch_trip_pdf(ctx, trip_uuid)
            if pdf:
                out_path.write_bytes(pdf)
                return True
            return False
        finally:
            try:
                ctx.close()
            except Exception:
                pass


def resolve_trip_uuid(tracker_url: str, *, headless: bool = True) -> str | None:
    """跟著 click-tracker 找出最終 trip UUID。"""
    import re
    from urllib.parse import unquote
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        try:
            ctx = browser.new_context()
            page = ctx.new_page()
            try:
                page.goto(tracker_url, wait_until="domcontentloaded", timeout=20_000)
                page.wait_for_timeout(1500)
            except Exception:
                pass
            url = page.url
            m = re.search(r"next_url=([^&]+)", url)
            if m:
                target = unquote(m.group(1))
                m2 = re.search(r"/trips/([0-9a-f-]+)", target)
                if m2:
                    return m2.group(1)
            m = re.search(r"/trips/([0-9a-f-]+)", url)
            return m.group(1) if m else None
        finally:
            browser.close()


def enrich_and_download(trips: list[dict], target_dir: Path | str, *, headless: bool = True) -> list[dict]:
    """對一批 trips（需含 _tracker_url 或 _trip_uuid）：
       1. 解析 UUID（如沒提供）
       2. 用同一個 browser context 下載每趟的 detail.pdf + invoices

    回傳 trips 加上 `_trip_uuid` `_detail_pdf` `_invoices` 欄位。
    """
    import re
    from urllib.parse import unquote

    target_dir = Path(target_dir).expanduser()
    target_dir.mkdir(parents=True, exist_ok=True)

    if not PROFILE_DIR.exists():
        for t in trips:
            t["_uber_browser_error"] = "尚未登入 Uber，請跑 uber_browser.py --setup"
        return trips

    with sync_playwright() as p:
        ctx = _launch_persistent(p, headless=headless, accept_downloads=True)
        try:
            for trip in trips:
                uuid = trip.get("_trip_uuid")
                if not uuid:
                    tracker = trip.get("_tracker_url")
                    if not tracker:
                        trip["_uber_browser_error"] = "信件沒有下載連結"
                        continue
                    # 登入狀態下 click-tracker 會直接 redirect 到 PDF 下載，page.url 變 about:blank。
                    # 改用 response 監聽抓中間經過的 URL（含 /trips/<uuid> 的）。
                    seen_urls: list[str] = []
                    pg = ctx.new_page()
                    pg.on("response", lambda r: seen_urls.append(r.url))
                    try:
                        try:
                            pg.goto(tracker, wait_until="domcontentloaded", timeout=20_000)
                        except Exception:
                            pass  # download 觸發會 raise，預期內
                        pg.wait_for_timeout(1500)
                    finally:
                        try:
                            pg.close()
                        except Exception:
                            pass
                    # 從所有 response URL 找出 UUID
                    for u in seen_urls:
                        m = re.search(r"/trips/([0-9a-f-]+)", u)
                        if m:
                            uuid = m.group(1)
                            break
                        m2 = re.search(r"next_url=([^&]+)", u)
                        if m2:
                            decoded = unquote(m2.group(1))
                            m3 = re.search(r"/trips/([0-9a-f-]+)", decoded)
                            if m3:
                                uuid = m3.group(1)
                                break
                    if not uuid:
                        trip["_uber_browser_error"] = f"無法解析 trip UUID（看到 {len(seen_urls)} 個 response）"
                        continue
                    trip["_trip_uuid"] = uuid

                # 下載 detail.pdf
                prefix = f"{uuid[:8]}-"
                pdf_bytes = _fetch_trip_pdf(ctx, uuid)
                if pdf_bytes:
                    detail_path = target_dir / f"{prefix}detail.pdf"
                    detail_path.write_bytes(pdf_bytes)
                    trip["_detail_pdf"] = str(detail_path)

                # 下載 invoices
                invs = _fetch_invoices(ctx, uuid)
                saved_invs = []
                for inv in invs:
                    if inv.get("bytes"):
                        label_safe = inv["label"].replace(" ", "")
                        inv_path = target_dir / f"{prefix}{label_safe}{inv['ext']}"
                        inv_path.write_bytes(inv["bytes"])
                        inv["path"] = str(inv_path)
                        inv.pop("bytes", None)
                        saved_invs.append(inv)
                trip["_invoices"] = saved_invs
        finally:
            try:
                ctx.close()
            except Exception:
                pass
    return trips


# ---------- CLI ----------

def main():
    import argparse
    p = argparse.ArgumentParser(description="Uber 官方收據下載工具（Playwright + persistent profile）")
    p.add_argument("--setup", action="store_true", help="開 headed 瀏覽器讓使用者登入 Uber")
    p.add_argument("--check", action="store_true", help="檢查 profile 是否仍然登入")
    p.add_argument("--download", metavar="UUID", help="下載指定 trip UUID 的收據 PDF")
    p.add_argument("--out", help="輸出 PDF 路徑（搭配 --download）")
    p.add_argument("--headed", action="store_true", help="（debug）downloader 用 headed 模式")
    args = p.parse_args()

    if args.setup:
        setup_login()
    elif args.check:
        print("✅ 已登入" if is_logged_in_quick() else "❌ 未登入（請跑 --setup）")
    elif args.download:
        if not args.out:
            print("--download 需搭配 --out", file=sys.stderr)
            sys.exit(1)
        ok = download_receipt(args.download, args.out, headless=not args.headed)
        if ok:
            print(f"✅ 已下載：{args.out}")
        else:
            print(f"❌ 下載失敗：{args.download}")
            sys.exit(1)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
