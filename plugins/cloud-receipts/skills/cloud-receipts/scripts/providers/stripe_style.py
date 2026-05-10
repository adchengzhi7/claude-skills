"""Stripe 標準收據 provider — Vercel / Supabase / Anthropic / Netlify 等共用模板。

寄件樣式：
    From:    "<Brand>" <invoice+statements@<domain>>
    Subject: Your receipt from <Brand> #YYYY-XXXX
    Body:    HTML
    Attachments:
       - Invoice-<acct>-NNNN.pdf
       - Receipt-YYYY-XXXX.pdf

只要每個 provider 提供 (name, display_name, sender, preferred Gmail accounts) 就夠。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from base.provider import AttachmentProvider


class StripeAttachmentProvider(AttachmentProvider):
    """Stripe 模板的共用 base — 子類只覆寫類別變數。"""

    sender: str = "invoice+statements@example.com"   # 子類覆寫

    @property
    def gmail_query(self) -> list[str]:
        return [f'FROM "{self.sender}"']

    def parse_subject(self, subject: str) -> dict:
        """
        範例 subject:
            'Your receipt from Vercel Inc. #XXXX-YYYY'
            'Your receipt from Anthropic, PBC #XXXX-YYYY-ZZZZ'
            'Payment received for Supabase Pte. Ltd. invoice (#XXXXXX-NNNNN)'
        """
        out: dict = {}
        m = re.search(r"#\s*([A-Z0-9\-]+)", subject)
        if m:
            out["invoice_number"] = m.group(1)
        return out


class VercelProvider(StripeAttachmentProvider):
    name = "vercel"
    display_name = "Vercel"
    sender = "invoice+statements@vercel.com"
    preferred_accounts: list[str] = []   # 兩個帳號都可能有，留空


class SupabaseProvider(StripeAttachmentProvider):
    name = "supabase"
    display_name = "Supabase"
    sender = "invoice+statements@supabase.com"


class AnthropicProvider(StripeAttachmentProvider):
    name = "anthropic"
    display_name = "Anthropic"
    sender = "invoice+statements@mail.anthropic.com"


class NetlifyProvider(StripeAttachmentProvider):
    name = "netlify"
    display_name = "Netlify"
    sender = "noreply@netlify.com"
