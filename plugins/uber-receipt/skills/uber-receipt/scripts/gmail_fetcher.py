"""從 Gmail IMAP 自動抓 Uber 行程收據 — 走 email-direct 路線。

認證：macOS Keychain（service `uber-receipt-gmail`，account = $USER 的 email）。
設定流程見 SKILL.md / README.md（先開 2FA → 建 App Password → keychain 存好）。

策略：
    Uber 行程信件本身的 HTML body 已含完整收據資料（金額、起訖、車牌、車隊）。
    所有 PDF 下載連結都是 click-tracker → riders.uber.com（需登入），
    無法用無痕方式抓 PDF。所以我們：

    1. IMAP 抓信
    2. 用 email_parser 直接解析 HTML
    3. 把原始 email 存成 .eml 檔（當報帳憑證 — 可在 Mail.app 開啟看完整 Uber 樣式）
    4. trip dict 的 source_path 指向 .eml 檔，後續 organize / report 流程不變

已處理紀錄：~/.config/receipts/uber-processed.json — 避免重複抓。
"""
from __future__ import annotations

import email
import email.policy
import imaplib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from email.message import EmailMessage
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterator

KEYCHAIN_SERVICE = "uber-receipt-gmail"
GMAIL_CONFIG = Path.home() / ".config" / "receipts" / "gmail.json"
PROCESSED_LOG = Path.home() / ".config" / "receipts" / "uber-processed.json"
IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993

# 用一個常見 desktop User-Agent，免得 Uber CDN 擋
HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/pdf,*/*",
}


# ---------- 認證 ----------

def _read_keychain(account: str) -> str | None:
    try:
        r = subprocess.run(
            ["security", "find-generic-password", "-a", account, "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True, text=True, check=True,
        )
        return r.stdout.strip() or None
    except subprocess.CalledProcessError:
        return None
    except FileNotFoundError:
        return None


def _load_gmail_config() -> dict:
    if not GMAIL_CONFIG.exists():
        return {}
    try:
        return json.loads(GMAIL_CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_gmail_email(addr: str) -> None:
    GMAIL_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    GMAIL_CONFIG.write_text(json.dumps({"email": addr}, indent=2), encoding="utf-8")
    try:
        GMAIL_CONFIG.chmod(0o600)
    except OSError:
        pass


def get_credentials() -> tuple[str, str] | None:
    """回傳 (email, app_password) 或 None（未設定）。"""
    cfg = _load_gmail_config()
    addr = cfg.get("email")
    if not addr:
        return None
    pw = _read_keychain(addr)
    if not pw:
        return None
    return addr, pw


def setup_instructions() -> str:
    return """
❌ Gmail 連線資訊未設定。請依以下三步驟建立：

1. 開 Gmail 2FA（如還沒開）：
   → https://myaccount.google.com/security

2. 建 App Password：
   → https://myaccount.google.com/apppasswords
   選 "Mail" / "Other (uber-receipt)"，複製 16 碼密碼（含空格沒關係）

3. 在 terminal 跑（把 your@email.com 與 16 碼換掉）：

   python3 -c "
   import sys
   sys.path.insert(0, '/Users/$USER/.claude/skills/uber-receipt/scripts')
   from gmail_fetcher import save_gmail_email
   save_gmail_email('your@email.com')
   "
   security add-generic-password -a 'your@email.com' -s 'uber-receipt-gmail' -w 'XXXX XXXX XXXX XXXX'

完成後重跑指令即可。
"""


# ---------- 處理紀錄 ----------

def _load_processed() -> set[str]:
    if not PROCESSED_LOG.exists():
        return set()
    try:
        data = json.loads(PROCESSED_LOG.read_text(encoding="utf-8"))
        return {entry["message_id"] for entry in data if "message_id" in entry}
    except Exception:
        return set()


def _append_processed(message_id: str, pdf_path: str | None) -> None:
    PROCESSED_LOG.parent.mkdir(parents=True, exist_ok=True)
    entries: list[dict] = []
    if PROCESSED_LOG.exists():
        try:
            entries = json.loads(PROCESSED_LOG.read_text(encoding="utf-8"))
        except Exception:
            entries = []
    entries.append({
        "message_id": message_id,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "pdf_path": pdf_path,
    })
    PROCESSED_LOG.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        PROCESSED_LOG.chmod(0o600)
    except OSError:
        pass


# ---------- IMAP ----------

def _imap_search_uber(M: imaplib.IMAP4_SSL, since: datetime | None) -> list[bytes]:
    """搜 Uber 行程信。回傳 IMAP UID list。"""
    M.select("INBOX", readonly=True)

    crit = ['FROM "noreply@uber.com"']
    if since:
        crit.append(f'SINCE {since.strftime("%d-%b-%Y")}')

    typ, data = M.uid("SEARCH", None, *crit)
    if typ != "OK":
        return []
    if not data or not data[0]:
        return []
    return data[0].split()


def _fetch_message(M: imaplib.IMAP4_SSL, uid: bytes) -> EmailMessage | None:
    typ, data = M.uid("FETCH", uid, "(RFC822)")
    if typ != "OK" or not data:
        return None
    raw = next((part[1] for part in data if isinstance(part, tuple)), None)
    if not raw:
        return None
    return email.message_from_bytes(raw, policy=email.policy.default)


# ---------- HTML 解析（找 PDF 下載 URL） ----------

class _LinkExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        for k, v in attrs:
            if k == "href" and v:
                self.urls.append(v)


def _extract_html(msg: EmailMessage) -> str:
    """抓信件 HTML 內文。"""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                try:
                    return part.get_content()
                except Exception:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        return payload.decode(charset, errors="replace")
        return ""
    if msg.get_content_type() == "text/html":
        try:
            return msg.get_content()
        except Exception:
            return ""
    return ""


def _extract_attachments(msg: EmailMessage) -> Iterator[tuple[str, bytes]]:
    """yield (filename, bytes) for 每個 PDF 附件。"""
    for part in msg.walk():
        if part.get_content_disposition() not in ("attachment", "inline"):
            continue
        filename = part.get_filename() or ""
        ctype = part.get_content_type()
        if not filename.lower().endswith(".pdf") and "pdf" not in ctype.lower():
            continue
        payload = part.get_payload(decode=True)
        if payload:
            yield (filename or "uber-receipt.pdf", payload)


def _candidate_receipt_urls(html: str) -> list[str]:
    """從 HTML 抽可能是 PDF 收據的 URL。

    Uber 信件常見的下載入口：
      - https://uber.com/.../trips/<uuid>/receipt
      - https://riders.uber.com/...
      - https://email.uber.com/wf/click?upn=...（click-tracker，會 302 到 PDF）
    """
    p = _LinkExtractor()
    p.feed(html)
    urls = []
    for url in p.urls:
        if not url.startswith("http"):
            continue
        # 過濾常見「不是 PDF」的連結
        skip_pat = (
            "facebook.com", "twitter.com", "instagram.com", "play.google.com",
            "apps.apple.com", "/unsubscribe", "uber.com/legal", "/privacy",
        )
        if any(s in url for s in skip_pat):
            continue
        # 收據相關關鍵字
        if any(kw in url.lower() for kw in ("receipt", "trip", "click")):
            urls.append(url)
    # 去重保序
    seen = set()
    out = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _try_download_pdf(url: str, timeout: int = 30) -> bytes | None:
    """跟著 redirect 拿 PDF bytes。回傳 None 如果不是 PDF 或失敗。"""
    req = urllib.request.Request(url, headers=HTTP_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ctype = resp.headers.get("Content-Type", "").lower()
            content = resp.read()
            if "pdf" in ctype or content[:4] == b"%PDF":
                return content
            return None
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return None


# ---------- 主流程 ----------

def fetch_trips(
    *,
    since: datetime | None = None,
    target_dir: Path | None = None,
    skip_processed: bool = True,
) -> list[dict]:
    """連 Gmail 抓 Uber 行程信，解析 + 存 .eml。

    回傳 trip dict 清單（與 parse.py 同 schema），每個有 source_path 指向 .eml 檔。
    額外 status 欄位: "parsed" / "skipped_processed" / "parse_failed"
    """
    sys.path.insert(0, str(Path(__file__).parent))
    from email_parser import parse_email, save_eml, extract_receipt_tracker, _extract_html_from_msg  # noqa: E402

    creds = get_credentials()
    if not creds:
        raise RuntimeError(setup_instructions())
    addr, pw = creds

    if target_dir is None:
        target_dir = Path("/tmp") / f"uber-fetch-{int(time.time())}"
    target_dir.mkdir(parents=True, exist_ok=True)

    processed = _load_processed() if skip_processed else set()
    results: list[dict] = []

    M = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    try:
        try:
            M.login(addr, pw)
        except imaplib.IMAP4.error as e:
            raise RuntimeError(
                f"❌ Gmail 登入失敗：{e}\n"
                f"   請確認 {addr} 的 App Password 是否正確（macOS Keychain service '{KEYCHAIN_SERVICE}'）。"
            )

        uids = _imap_search_uber(M, since)
        print(f"📧 IMAP 找到 {len(uids)} 封 Uber 信件"
              + (f"（since {since.date()}）" if since else ""))

        for uid in uids:
            uid_str = uid.decode()
            if uid_str in processed:
                results.append({"uid": uid_str, "status": "skipped_processed", "source_path": None})
                continue

            msg = _fetch_message(M, uid)
            if not msg:
                results.append({"uid": uid_str, "status": "parse_failed", "source_path": None})
                continue

            # 暫存 .eml 到 target_dir
            eml_path = target_dir / f"uber-{uid_str}.eml"
            save_eml(msg, eml_path)

            try:
                trip = parse_email(msg, eml_source_path=str(eml_path))
            except Exception as e:
                results.append({"uid": uid_str, "status": "parse_failed",
                                "source_path": str(eml_path), "error": str(e)})
                _append_processed(uid_str, str(eml_path))
                continue

            if trip.get("is_eats"):
                continue

            # 順手抽 click-tracker URL 給 uber_browser 後續用
            try:
                html = _extract_html_from_msg(msg)
                trip["_tracker_url"] = extract_receipt_tracker(html)
            except Exception:
                trip["_tracker_url"] = None

            trip["uid"] = uid_str
            trip["status"] = "parsed"
            results.append(trip)
            _append_processed(uid_str, str(eml_path))

    finally:
        try:
            M.close()
        except Exception:
            pass
        M.logout()

    return results


# 舊 API 別名（給呼叫者過渡用）
fetch_pdfs = fetch_trips


# ---------- CLI ----------

def main():
    import argparse
    p = argparse.ArgumentParser(description="從 Gmail IMAP 抓 Uber 收據 PDF")
    p.add_argument("--since", help="只抓這個日期之後的信件 (YYYY-MM-DD)，預設 60 天前")
    p.add_argument("--target", help="PDF 存到這個資料夾，預設 /tmp/uber-fetch-{ts}/")
    p.add_argument("--all", action="store_true", help="略過 processed log，重抓全部")
    p.add_argument("--check", action="store_true", help="只檢查認證設定")
    args = p.parse_args()

    if args.check:
        creds = get_credentials()
        if creds:
            addr, _ = creds
            print(f"✅ Gmail 設定 OK：{addr}")
            print(f"   keychain service: {KEYCHAIN_SERVICE}")
            print(f"   processed log: {PROCESSED_LOG} ({len(_load_processed())} 筆已處理)")
        else:
            print(setup_instructions())
            sys.exit(1)
        return

    since = None
    if args.since:
        since = datetime.fromisoformat(args.since)
    else:
        since = datetime.now() - timedelta(days=60)

    target = Path(args.target).expanduser().resolve() if args.target else None

    try:
        results = fetch_trips(since=since, target_dir=target, skip_processed=not args.all)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    by_status: dict[str, int] = {}
    for r in results:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1

    print(f"\n📊 結果：{by_status}")
    for r in results:
        if r["status"] == "parsed":
            route = f"{r.get('from_short') or '?'} → {r.get('to_short') or '?'}"
            print(f"   ✅ {r.get('trip_date')} {r.get('trip_time_start')} {route} ${r.get('total')}  →  {r['source_path']}")
        elif r["status"] == "parse_failed":
            print(f"   ⚠️  UID {r['uid']} parse 失敗")


if __name__ == "__main__":
    main()
