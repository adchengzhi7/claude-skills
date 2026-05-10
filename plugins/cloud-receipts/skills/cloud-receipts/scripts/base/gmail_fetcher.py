"""多帳號 Gmail IMAP 抓信。

設計：
    ~/.config/receipts/gmail.json:
        {
          "accounts": [
            {"email": "personal@example.com", "label": "personal"},
            {"email": "dev@example.com", "label": "dev"}
          ]
        }
    macOS Keychain：每個 email 一筆 App Password
        service = "cloud-receipts-gmail"
        account = email

向下相容：舊版 `uber-receipt-gmail` 也認（migration helper）。
"""
from __future__ import annotations

import email
import email.policy
import imaplib
import json
import subprocess
import sys
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Iterable, Iterator

KEYCHAIN_SERVICE = "cloud-receipts-gmail"
LEGACY_KEYCHAIN_SERVICES = ["uber-receipt-gmail"]
GMAIL_CONFIG = Path.home() / ".config" / "receipts" / "gmail.json"
PROCESSED_LOG_DIR = Path.home() / ".config" / "receipts"
IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993


# ---------- 認證 ----------

def _read_keychain(account: str, service: str = KEYCHAIN_SERVICE) -> str | None:
    try:
        r = subprocess.run(
            ["security", "find-generic-password", "-a", account, "-s", service, "-w"],
            capture_output=True, text=True, check=True,
        )
        return r.stdout.strip() or None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _read_password(email_addr: str) -> str | None:
    pw = _read_keychain(email_addr, KEYCHAIN_SERVICE)
    if pw:
        return pw
    for legacy in LEGACY_KEYCHAIN_SERVICES:
        pw = _read_keychain(email_addr, legacy)
        if pw:
            return pw
    return None


def save_password(email_addr: str, password: str) -> None:
    subprocess.run(
        ["security", "add-generic-password",
         "-a", email_addr, "-s", KEYCHAIN_SERVICE, "-w", password, "-U"],
        check=True, capture_output=True,
    )


def load_accounts() -> list[dict]:
    """回傳 [{email, label, _password}, ...]。沒設定回 []。

    向下相容舊 gmail.json 的單一 email 格式：{"email": "x@y"}。
    """
    if not GMAIL_CONFIG.exists():
        return []
    try:
        data = json.loads(GMAIL_CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return []

    if isinstance(data, dict) and "email" in data and "accounts" not in data:
        accounts = [{"email": data["email"], "label": "default"}]
    elif isinstance(data, dict) and "accounts" in data:
        accounts = data["accounts"]
    else:
        return []

    out = []
    for acc in accounts:
        if not isinstance(acc, dict) or "email" not in acc:
            continue
        pw = _read_password(acc["email"])
        if pw:
            out.append({**acc, "_password": pw})
    return out


def save_accounts(accounts: list[dict]) -> None:
    GMAIL_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    cleaned = [{k: v for k, v in a.items() if not k.startswith("_")} for a in accounts]
    GMAIL_CONFIG.write_text(
        json.dumps({"accounts": cleaned}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    try:
        GMAIL_CONFIG.chmod(0o600)
    except OSError:
        pass


def add_account(email_addr: str, label: str = "default") -> None:
    """加新 Gmail 帳號（保留現有，避免重覆）。"""
    raw = {}
    if GMAIL_CONFIG.exists():
        try:
            raw = json.loads(GMAIL_CONFIG.read_text(encoding="utf-8"))
        except Exception:
            raw = {}
    accounts = raw.get("accounts") or ([{"email": raw["email"], "label": "default"}] if raw.get("email") else [])
    if not any(a.get("email") == email_addr for a in accounts):
        accounts.append({"email": email_addr, "label": label})
    save_accounts(accounts)


def setup_instructions(email_addr: str | None = None) -> str:
    target = email_addr or "your@email.com"
    return f"""
❌ Gmail 連線資訊未設定。請依以下步驟建立：

1. 開 2FA：https://myaccount.google.com/security
2. 建 App Password：https://myaccount.google.com/apppasswords
   App name: cloud-receipts，複製 16 碼

3. terminal 執行（替換 EMAIL 與 PASSWORD）：
   python3 -c "
   import sys; sys.path.insert(0, '$HOME/.claude/skills/cloud-receipts/scripts')
   from base.gmail_fetcher import add_account, save_password
   add_account('{target}')
   "
   security add-generic-password \\
     -a '{target}' -s 'cloud-receipts-gmail' \\
     -w 'XXXX XXXX XXXX XXXX' -U
"""


# ---------- 已處理紀錄（每個 provider 獨立） ----------

def processed_log_path(provider: str) -> Path:
    return PROCESSED_LOG_DIR / f"{provider}-processed.json"


def load_processed(provider: str) -> set[str]:
    path = processed_log_path(provider)
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {entry["uid"] for entry in data if "uid" in entry}
    except Exception:
        return set()


def append_processed(provider: str, uid: str, account_email: str, archived_path: str | None = None) -> None:
    path = processed_log_path(provider)
    path.parent.mkdir(parents=True, exist_ok=True)
    entries: list[dict] = []
    if path.exists():
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            entries = []
    entries.append({
        "uid": uid,
        "account": account_email,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "archived_path": archived_path,
    })
    path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


# ---------- IMAP fetch ----------

def search_account(
    account: dict,
    *,
    query_parts: list[str],
    since: datetime | None = None,
) -> tuple[imaplib.IMAP4_SSL, list[bytes]]:
    """連線 + SEARCH。回傳 (open IMAP connection, UID list)，呼叫端要負責 close/logout。"""
    M = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    M.login(account["email"], account["_password"])
    M.select("INBOX", readonly=True)

    crit = list(query_parts)
    if since:
        crit.append(f'SINCE {since.strftime("%d-%b-%Y")}')
    typ, data = M.uid("SEARCH", None, *crit)
    uids = data[0].split() if (typ == "OK" and data and data[0]) else []
    return M, uids


def fetch_message(M: imaplib.IMAP4_SSL, uid: bytes) -> EmailMessage | None:
    typ, data = M.uid("FETCH", uid, "(RFC822)")
    if typ != "OK" or not data:
        return None
    raw = next((part[1] for part in data if isinstance(part, tuple)), None)
    if not raw:
        return None
    return email.message_from_bytes(raw, policy=email.policy.default)


def iter_provider_emails(
    provider_name: str,
    accounts: list[dict],
    *,
    query_parts: list[str],
    since: datetime | None,
    skip_processed: bool = True,
) -> Iterator[tuple[str, str, EmailMessage]]:
    """yield (account_email, uid_str, EmailMessage) for 各帳號裡符合條件的信件。"""
    processed = load_processed(provider_name) if skip_processed else set()

    for acc in accounts:
        try:
            M, uids = search_account(acc, query_parts=query_parts, since=since)
        except Exception as e:
            print(f"⚠️ {acc['email']} 連線失敗：{e}", file=sys.stderr)
            continue
        try:
            for uid in uids:
                key = f"{acc['email']}:{uid.decode()}"
                if key in processed:
                    continue
                msg = fetch_message(M, uid)
                if not msg:
                    continue
                yield acc["email"], uid.decode(), msg
        finally:
            try:
                M.close()
            except Exception:
                pass
            M.logout()
