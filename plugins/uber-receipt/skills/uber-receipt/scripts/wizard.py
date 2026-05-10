"""新手入門 wizard — 引導使用者一次性完成所有 setup。

5 步：
    1. 檢查 Python deps（pdfplumber, playwright, chromium）
    2. Gmail：開 App Password 頁、引導建、存 Keychain、IMAP 測試
    3. Uber：開瀏覽器讓使用者登入、自動偵測完成
    4. 公司清單：拿 1 個統編 → GCIS 反查 → 寫入 companies.json
    5. Dry-run：抓最近 30 天 Uber、列表給看、不歸檔

每步失敗都有可操作的提示。整段約 5 分鐘。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


SECTION = "─" * 60


def _input(prompt: str, allow_empty: bool = False, secret: bool = False) -> str:
    if secret:
        try:
            import getpass
            return getpass.getpass(prompt).strip()
        except (KeyboardInterrupt, EOFError):
            print("\n👋 中斷")
            sys.exit(1)
    while True:
        try:
            v = input(prompt).strip()
        except (KeyboardInterrupt, EOFError):
            print("\n👋 中斷")
            sys.exit(1)
        if v or allow_empty:
            return v


def _yes(prompt: str, default: bool = True) -> bool:
    suffix = " [Y/n] " if default else " [y/N] "
    v = _input(prompt + suffix, allow_empty=True).lower()
    if not v:
        return default
    return v in ("y", "yes", "是", "好", "1", "true")


# ---------- Step 1：deps ----------

def step_1_check_deps():
    print(f"\n{SECTION}\n[1/5] 檢查 Python 套件\n{SECTION}")
    needed = {
        "pdfplumber": "pdfplumber",
        "playwright": "playwright",
    }
    missing = []
    for mod, pkg in needed.items():
        try:
            __import__(mod)
            print(f"   ✅ {mod}")
        except ImportError:
            print(f"   ❌ {mod}（缺）")
            missing.append(pkg)

    if missing:
        if not _yes(f"\n要 pip 安裝 {missing} 嗎？"):
            print("⚠️ 沒裝完整 deps 後續會失敗")
            return False
        try:
            subprocess.run([sys.executable, "-m", "pip", "install",
                            "--break-system-packages"] + missing, check=True)
        except subprocess.CalledProcessError:
            print("❌ pip install 失敗，請手動跑：")
            print(f"   pip3 install --break-system-packages {' '.join(missing)}")
            return False

    # Chromium 是 playwright 內附 binary，要另外裝
    chromium_dirs = list(Path.home().glob("Library/Caches/ms-playwright/chromium-*"))
    if not chromium_dirs:
        print("\n   📦 安裝 Chromium 瀏覽器（Playwright 用）...")
        try:
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        except subprocess.CalledProcessError:
            print("❌ Chromium 安裝失敗")
            return False
    else:
        print(f"   ✅ chromium")

    return True


# ---------- Step 2：Gmail ----------

def step_2_gmail():
    from gmail_fetcher import save_gmail_email, get_credentials, KEYCHAIN_SERVICE, IMAP_HOST, IMAP_PORT

    print(f"\n{SECTION}\n[2/5] Gmail 連線設定\n{SECTION}")

    creds = get_credentials()
    if creds:
        print(f"   ✅ 已設定 ({creds[0]})。要重設嗎？")
        if not _yes("重設？", default=False):
            return True

    print("\n📧 你需要先建一個 Gmail App Password：")
    print("   1. 開 https://myaccount.google.com/apppasswords")
    print("      （需先開 2FA — https://myaccount.google.com/security ）")
    print("   2. App name 填 'uber-receipt'，建立")
    print("   3. 複製 16 碼密碼（格式 'xxxx xxxx xxxx xxxx'）\n")

    if not _yes("繼續？", default=True):
        return False

    email_addr = _input("   你的 Gmail 信箱 (e.g. you@gmail.com): ")
    pw = _input("   貼入 App Password (輸入時不顯示): ", secret=True)

    if not pw:
        print("❌ 沒輸入 password")
        return False

    save_gmail_email(email_addr)
    try:
        subprocess.run(
            ["security", "add-generic-password",
             "-a", email_addr, "-s", KEYCHAIN_SERVICE, "-w", pw, "-U"],
            check=True, capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"❌ Keychain 寫入失敗：{e.stderr.decode() if e.stderr else e}")
        return False

    print(f"\n   🔌 測試 IMAP 連線到 {IMAP_HOST}:{IMAP_PORT}...")
    try:
        import imaplib
        M = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        M.login(email_addr, pw)
        M.logout()
        print(f"   ✅ Gmail 連線 OK")
        return True
    except Exception as e:
        msg = str(e)
        print(f"   ❌ 連線失敗：{msg}")
        if "AUTHENTICATIONFAILED" in msg:
            print("      → App Password 可能輸入錯誤，或公司 Workspace 禁用 App Password")
        return False


# ---------- Step 3：Uber ----------

def step_3_uber():
    from uber_browser import setup_login, is_logged_in_quick, PROFILE_DIR

    print(f"\n{SECTION}\n[3/5] Uber 登入\n{SECTION}")

    if PROFILE_DIR.exists() and is_logged_in_quick():
        print("   ✅ 已登入過（profile 內有 session）")
        if not _yes("重新登入？", default=False):
            return True

    print("\n🌐 即將開啟 Chrome 視窗")
    print("   1. 在開啟的視窗登入 riders.uber.com")
    print("   2. 看到 trips 列表後，視窗會 3 秒後自動關閉")
    print("   （或你也可以手動關，session 都會存）\n")

    if not _yes("開始？"):
        return False

    setup_login(auto_close_seconds=3, max_wait_seconds=600)
    return is_logged_in_quick()


# ---------- Step 4：公司清單 ----------

def step_4_companies():
    from companies import load_companies, write_companies, PRIMARY_PATH

    print(f"\n{SECTION}\n[4/5] 公司清單\n{SECTION}")

    existing = load_companies()
    if existing:
        print(f"   ✅ 已有 {len(existing)} 筆：")
        for c in existing:
            print(f"      • {c['label']}  [{c['tax_id']}]  {c['name']}")
        if not _yes("\n要再新增嗎？", default=False):
            return True

    print("\n💼 你最常請款的公司是哪一家？只要統編，自動反查全名。")

    while True:
        tax_id = _input("   統編（8 碼數字）: ").strip()
        if not tax_id:
            print("⚠️ 跳過公司清單建立 — 後續可手動編輯 ~/.config/receipts/companies.json")
            return True
        if not (tax_id.isdigit() and len(tax_id) == 8):
            print("   ❌ 統編應為 8 位數字，再試一次")
            continue

        # GCIS 反查
        url = (
            "https://data.gcis.nat.gov.tw/od/data/api/"
            "5F64D864-61CB-4D0D-8AD9-492047CC1EA6"
            f"?$format=json&$filter=Business_Accounting_NO eq {tax_id}&$top=5"
        )
        try:
            with urllib.request.urlopen(urllib.parse.quote(url, safe=":/?$=&"), timeout=10) as r:
                data = json.loads(r.read())
        except Exception as e:
            print(f"   ⚠️ GCIS 反查失敗：{e}")
            data = []

        if data:
            name = data[0].get("Company_Name", "")
            print(f"   ✅ 反查結果：{name}")
            if _yes(f"   用此名稱？", default=True):
                full_name = name
            else:
                full_name = _input("   手動輸入全名: ")
        else:
            print(f"   ⚠️ 查無資料（或公司未公示），手動輸入")
            full_name = _input("   公司全名: ")

        label = _input(f"   你習慣的簡稱 (預設: {full_name[:4] if full_name else '我的公司'}): ", allow_empty=True)
        if not label:
            label = (full_name[:4] or "我的公司") if full_name else "我的公司"

        existing.append({"label": label, "tax_id": tax_id, "name": full_name or label})
        write_companies(existing)
        print(f"   ✅ 已寫入 {PRIMARY_PATH}")

        if not _yes("\n   再加一家？", default=False):
            return True


# ---------- Step 5：Dry-run ----------

def step_5_dry_run():
    print(f"\n{SECTION}\n[5/5] Dry-run（試跑，不歸檔）\n{SECTION}")

    if not _yes("抓最近 30 天 Gmail Uber 信件試跑看看？"):
        print("\n📋 Setup 完成！日後直接跑：")
        print("   python3 ~/.claude/skills/uber-receipt/scripts/main.py --from-gmail")
        return True

    from datetime import datetime, timedelta
    from gmail_fetcher import fetch_trips
    since = datetime.now() - timedelta(days=30)
    print(f"   📧 抓 since {since.date()} ...")
    trips = fetch_trips(since=since, skip_processed=False)
    parsed = [t for t in trips if t.get("status") == "parsed"]
    print(f"\n   抓到 {len(parsed)} 趟 Uber 行程：\n")
    for i, t in enumerate(parsed, 1):
        print(f"   {i}. {t.get('trip_date')} {t.get('trip_time_start')} "
              f"{t.get('from_short')} → {t.get('to_short')} ${t.get('total')}")
    return True


# ---------- 入口 ----------

def run():
    print("=" * 60)
    print("  uber-receipt 新手 setup wizard")
    print("=" * 60)
    print("約 5 分鐘走完。每步都可中斷重試。\n")

    steps = [
        ("Python 套件", step_1_check_deps),
        ("Gmail 連線", step_2_gmail),
        ("Uber 登入", step_3_uber),
        ("公司清單", step_4_companies),
        ("Dry-run", step_5_dry_run),
    ]
    completed = []
    for name, fn in steps:
        try:
            ok = fn()
        except Exception as e:
            print(f"❌ {name} 失敗：{e}")
            ok = False
        if not ok:
            print(f"\n⚠️ [{name}] 沒完成。可重跑 `--wizard` 從這步繼續。")
            print(f"已完成：{', '.join(completed) or '無'}")
            return
        completed.append(name)

    print(f"\n{'=' * 60}")
    print("🎉 全部完成！")
    print(f"{'=' * 60}\n")
    print("接下來你可以：")
    print("  • 跟 Claude 說「整理 Uber 收據」 — 全自動跑")
    print("  • 或在 terminal 跑 `python3 ~/.claude/skills/uber-receipt/scripts/main.py --from-gmail`")
    print("\n所有檔案會出現在 ~/Downloads/uber_receipts/YYYY-MM/YYYY-MM-DD/")


if __name__ == "__main__":
    run()
