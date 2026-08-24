"""cloud-receipts CLI — 多 provider 收據自動整理。

用法：
    python3 main.py --list                       # 列 provider
    python3 main.py --setup                      # 跑 wizard
    python3 main.py vercel --from-gmail          # 抓特定 provider
    python3 main.py all --from-gmail             # 三家全部
    python3 main.py vercel --from-gmail --dry-run
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from base.companies import get_company_by_tax_id, list_summary, load_companies
from base.gmail_fetcher import (
    iter_provider_emails,
    load_accounts,
    setup_instructions,
    append_processed,
)
from base.organize import organize as do_organize
from base.provider import BaseProvider
from providers import REGISTRY, get_provider, list_provider_names


def _list():
    print("可用的 provider：")
    for name in list_provider_names():
        p = get_provider(name)
        accs = (", ".join(p.preferred_accounts) if p.preferred_accounts else "all")
        print(f"  • {p.name:<10} {p.display_name:<15} sender: {p.sender}  accounts: {accs}")
    print(f"\n{list_summary()}")
    accounts = load_accounts()
    print(f"\n📧 Gmail accounts: {len(accounts)}")
    for a in accounts:
        print(f"   • {a['email']}  ({a.get('label')})")


def _filter_accounts(provider: BaseProvider, all_accounts: list[dict]) -> list[dict]:
    if not provider.preferred_accounts:
        return all_accounts
    return [a for a in all_accounts if a["email"] in provider.preferred_accounts]


def _run_provider(provider_name: str, args) -> dict:
    provider = get_provider(provider_name)
    if not provider:
        print(f"❌ 不認得 provider：{provider_name}", file=sys.stderr)
        return {"error": "unknown_provider"}

    accounts = load_accounts()
    if not accounts:
        print(setup_instructions(), file=sys.stderr)
        return {"error": "no_accounts"}

    accounts = _filter_accounts(provider, accounts)
    if not accounts:
        print(f"⚠️ 沒有適合的 Gmail 帳號（preferred: {provider.preferred_accounts}）")
        return {"error": "no_matching_accounts"}

    since = (datetime.fromisoformat(args.since) if args.since
             else datetime.now() - timedelta(days=180))

    print(f"\n🔍 [{provider.display_name}] 抓 since {since.date()}")
    records = []
    company_lookup = {c["tax_id"]: c["label"] for c in load_companies()}

    for account_email, uid, msg in iter_provider_emails(
        provider.name,
        accounts,
        query_parts=provider.gmail_query,
        since=since,
        skip_processed=not args.refetch,
    ):
        try:
            record = provider.parse(msg, account_email, uid)
        except Exception as e:
            print(f"   ⚠️ parse 失敗 {account_email}/{uid}: {e}", file=sys.stderr)
            continue
        if not record.documents:
            print(f"   ⚠️ {account_email}/{uid}: 無附件，略過")
            continue
        records.append(record)

    print(f"   抓到 {len(records)} 張 invoice email")

    # 歸檔
    saved = []
    for rec in records:
        result = do_organize(rec, provider, overwrite=args.overwrite, dry_run=args.dry_run)
        for action in result["actions"]:
            print(f"   {action['action']:>14}  {Path(action['target']).name}")
        if not args.dry_run and any(a["action"] in ("created", "overwritten") for a in result["actions"]):
            append_processed(provider.name, rec.uid, rec.account_email,
                             archived_path=result["target_dir"])
            saved.append(result)

    return {"provider": provider.name, "count": len(records), "saved": len(saved)}


def main():
    p = argparse.ArgumentParser(description="cloud-receipts — 多 provider 收據自動整理")
    p.add_argument("provider", nargs="?", help="provider 名稱（vercel/supabase/anthropic/netlify/all）")
    p.add_argument("--list", action="store_true", help="列出所有 provider")
    p.add_argument("--setup", "--wizard", action="store_true", help="跑 setup wizard")
    p.add_argument("--from-gmail", action="store_true", help="從 Gmail 抓 + 歸檔")
    p.add_argument("--since", metavar="YYYY-MM-DD", help="只抓這日期之後的（預設 180 天）")
    p.add_argument("--refetch", action="store_true", help="略過已處理紀錄重抓")
    p.add_argument("--overwrite", action="store_true", help="目標檔已存在時強制覆蓋")
    p.add_argument("--dry-run", action="store_true", help="試跑不寫檔")

    args = p.parse_args()

    if args.list:
        _list()
        return

    if args.setup:
        try:
            from wizard import run as run_wizard
            run_wizard()
        except ImportError:
            print("📋 Setup（wizard.py 尚未建立，請手動跑下面命令）：\n")
            print("  EMAIL='your@gmail.com'")
            print("  PW='XXXX XXXX XXXX XXXX'  # https://myaccount.google.com/apppasswords")
            print("  python3 -c \"")
            print("  import sys; sys.path.insert(0, '<本 skill 的 scripts 目錄>')")
            print("  from base.gmail_fetcher import add_account; add_account('$EMAIL')")
            print("  \"")
            print("  security add-generic-password -a \"$EMAIL\" -s 'cloud-receipts-gmail' -w \"$PW\" -U")
            print("\n見 README.md")
        return

    if not args.provider:
        p.print_help()
        sys.exit(1)

    if args.provider == "all":
        for name in list_provider_names():
            print(f"\n{'='*60}\n  {name}\n{'='*60}")
            _run_provider(name, args)
        return

    _run_provider(args.provider, args)


if __name__ == "__main__":
    main()
