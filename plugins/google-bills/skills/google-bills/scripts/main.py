"""google-bills 主入口。

從 Gmail 抓 payments-noreply@google.com 的帳單 PDF，依 subject 分類：
    - 「Google Workspace」 → ~/Downloads/google_bills/workspace/YYYY-MM/
    - 「Google Cloud Platform」 / 「GCP」 → ~/Downloads/google_bills/gcp/YYYY-MM/
    - 其他 → ~/Downloads/google_bills/other/YYYY-MM/

PDF 檔名沿用附件原檔名（Google 給的純數字 invoice ID）。
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from pathlib import Path

# 重用 cloud-receipts 的 base 模組
sys.path.insert(0, str(Path(__file__).resolve().parent))  # base/ 模組隨包附帶，不依賴安裝位置

from base.gmail_fetcher import (  # noqa: E402
    iter_provider_emails,
    load_accounts,
    setup_instructions,
    append_processed,
    load_processed,
)

GOOGLE_SENDER = "payments-noreply@google.com"
ARCHIVE_ROOT = Path.home() / "Downloads" / "google_bills"
PROVIDER_KEY = "google-bills"


# Subject 分類規則
SUB_RULES = [
    ("workspace", re.compile(r"Google\s*Workspace", re.IGNORECASE)),
    ("gcp",       re.compile(r"Google\s*Cloud\s*Platform|GCP|APIs", re.IGNORECASE)),
]


def classify_subject(subject: str) -> str:
    if not subject:
        return "other"
    for cat, pat in SUB_RULES:
        if pat.search(subject):
            return cat
    return "other"


def extract_pdf_attachments(msg: EmailMessage):
    """yield (filename, bytes) for 每個 PDF 附件。"""
    for part in msg.walk():
        cd = part.get_content_disposition()
        if cd not in ("attachment", "inline"):
            continue
        filename = part.get_filename() or ""
        ctype = (part.get_content_type() or "").lower()
        if not (filename.lower().endswith(".pdf") or "pdf" in ctype):
            continue
        payload = part.get_payload(decode=True)
        if payload:
            yield (filename or "google-bill.pdf", payload)


def parse_email_date(msg: EmailMessage) -> str | None:
    raw = msg.get("Date", "")
    try:
        dt = parsedate_to_datetime(raw)
        return dt.strftime("%Y-%m-%d") if dt else None
    except Exception:
        return None


def archive_dir(category: str, date_str: str | None) -> Path:
    base = ARCHIVE_ROOT / category
    if date_str and len(date_str) >= 7:
        base = base / date_str[:7]
    else:
        base = base / "unknown-month"
    return base


def safe_filename(name: str) -> str:
    name = re.sub(r"[\\/:*?\"<>|]+", "-", name).strip()
    return name or "google-bill.pdf"


def main():
    p = argparse.ArgumentParser(description="抓 Google Workspace / GCP 帳單")
    p.add_argument("--since", metavar="YYYY-MM-DD", help="只抓這日期之後（預設 180 天）")
    p.add_argument("--refetch", action="store_true", help="略過 processed log 重抓")
    p.add_argument("--overwrite", action="store_true", help="目標檔已存在時覆蓋")
    p.add_argument("--dry-run", action="store_true", help="試跑不寫檔")
    args = p.parse_args()

    accounts = load_accounts()
    if not accounts:
        print(setup_instructions(), file=sys.stderr)
        sys.exit(1)

    since = (datetime.fromisoformat(args.since) if args.since
             else datetime.now() - timedelta(days=180))

    print(f"🔍 抓 Google Payments 帳單 since {since.date()}（{len(accounts)} 個 Gmail 帳號）")

    counts: dict[str, int] = {"workspace": 0, "gcp": 0, "other": 0, "skipped": 0}

    for account_email, uid, msg in iter_provider_emails(
        PROVIDER_KEY,
        accounts,
        query_parts=[f'FROM "{GOOGLE_SENDER}"'],
        since=since,
        skip_processed=not args.refetch,
    ):
        subject = msg.get("Subject", "")
        date = parse_email_date(msg)
        category = classify_subject(subject)

        attachments = list(extract_pdf_attachments(msg))
        if not attachments:
            counts["skipped"] += 1
            print(f"   ⏭ {account_email}/{uid} 無 PDF 附件，略過：{subject[:60]}")
            continue

        target_dir = archive_dir(category, date)
        if not args.dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)

        archived_paths = []
        for fname, content in attachments:
            target = target_dir / safe_filename(fname)
            if target.exists() and not args.overwrite:
                print(f"   ⏭ {target.name}（已存在，--overwrite 才覆蓋）")
                continue
            if args.dry_run:
                print(f"   📋 would_write [{category}] {target}")
            else:
                target.write_bytes(content)
                print(f"   ✅ [{category}] {target}")
            archived_paths.append(str(target))

        if archived_paths and not args.dry_run:
            append_processed(PROVIDER_KEY, uid, account_email,
                             archived_path=str(target_dir))

        counts[category] = counts.get(category, 0) + 1

    print("\n📊 結果：")
    for k, v in counts.items():
        print(f"   {k:>10}: {v}")
    print(f"\n   📁 歸檔位置：{ARCHIVE_ROOT}")


if __name__ == "__main__":
    main()
