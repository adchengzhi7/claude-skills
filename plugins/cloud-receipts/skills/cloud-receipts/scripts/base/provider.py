"""Provider 抽象介面 + 兩個常見 base class。

每個 provider 實作 4 件事：
    1. 知道哪些 IMAP 信件是該 provider 的 invoice
    2. 知道怎麼從信件取得 invoice 文件（attachment / 登入下載 / etc.）
    3. 知道怎麼解析文件得到 metadata（date / amount / invoice number）
    4. 知道歸檔規則（檔名 / 目錄）

兩個 base class：
    - AttachmentProvider: 信件直接含 PDF 附件（Supabase / Anthropic / Netlify / Stripe-style）
    - DashboardProvider: 信件僅有 link，需登入下載（Uber-style）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Optional


@dataclass
class Document:
    """單一收據文件（PDF / XML / HTML）。"""
    filename: str           # 原始檔名 e.g. Invoice-XXX.pdf
    content: bytes          # 檔案內容
    role: str = "invoice"   # invoice | receipt | detail | misc
    ext: str = ""           # .pdf / .xml / .html

    def __post_init__(self):
        if not self.ext:
            self.ext = Path(self.filename).suffix.lower() or ".pdf"


@dataclass
class InvoiceRecord:
    """從信件 + 文件解析出的 invoice 紀錄。"""
    provider: str                          # "supabase" / "uber" / etc.
    account_email: str                     # 抓自哪個 Gmail
    uid: str                               # IMAP UID
    invoice_date: Optional[str] = None     # YYYY-MM-DD
    invoice_number: Optional[str] = None   # e.g. "ABCDEF-00010"
    total_amount: Optional[str] = None     # e.g. "25.00 USD"
    currency: Optional[str] = None
    subject: Optional[str] = None
    documents: list[Document] = field(default_factory=list)
    suggested_company: Optional[str] = None  # 反查 companies.json 後填
    extra: dict = field(default_factory=dict)  # provider-specific 額外資訊


class BaseProvider:
    """所有 provider 的 base。"""
    name: str = "base"
    display_name: str = "Base"
    gmail_query: list[str] = []           # IMAP search criteria
    preferred_accounts: list[str] = []    # 只在這些帳號搜，空 = 全部
    _archive_root_subdir: str = "cloud_receipts"  # ~/Downloads/<subdir>/

    def matches_account(self, email: str) -> bool:
        return not self.preferred_accounts or email in self.preferred_accounts

    def parse(self, msg: EmailMessage, account_email: str, uid: str) -> InvoiceRecord:
        """子類覆寫：信件 → InvoiceRecord（含 metadata + documents）。"""
        raise NotImplementedError

    def archive_dir(self, record: InvoiceRecord) -> Path:
        """歸檔目錄。預設按 `~/Downloads/cloud_receipts/<provider>/YYYY-MM/`。"""
        root = Path.home() / "Downloads" / self._archive_root_subdir / self.name
        if record.invoice_date and len(record.invoice_date) >= 7:
            root = root / record.invoice_date[:7]
        return root

    def filename_for(self, record: InvoiceRecord, doc: Document) -> str:
        """單檔在歸檔目錄內的最終檔名。"""
        date = record.invoice_date or "unknown-date"
        inv = record.invoice_number or "unknown-no"
        company = f"-[{record.suggested_company}]" if record.suggested_company else ""
        return f"{date}-{self.display_name}-{inv}-{doc.role}{company}{doc.ext}"


class AttachmentProvider(BaseProvider):
    """信件直接含 PDF 附件 — Supabase / Anthropic / Netlify / 標準 Stripe 模式。"""

    def extract_attachments(self, msg: EmailMessage) -> list[Document]:
        out: list[Document] = []
        for part in msg.walk():
            cd = part.get_content_disposition()
            if cd not in ("attachment", "inline"):
                continue
            filename = part.get_filename() or ""
            ctype = (part.get_content_type() or "").lower()
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            if filename.lower().endswith(".pdf") or "pdf" in ctype:
                role = self._infer_role(filename)
                out.append(Document(filename=filename or "attachment.pdf",
                                    content=payload, role=role, ext=".pdf"))
            elif filename.lower().endswith(".xml") or "xml" in ctype:
                role = self._infer_role(filename)
                out.append(Document(filename=filename, content=payload,
                                    role=role, ext=".xml"))
        return out

    @staticmethod
    def _infer_role(filename: str) -> str:
        f = filename.lower()
        if "receipt" in f:
            return "receipt"
        if "invoice" in f:
            return "invoice"
        if "detail" in f or "trip" in f:
            return "detail"
        return "invoice"

    def parse_subject(self, subject: str) -> dict:
        """子類可覆寫：從 Subject 抽 invoice number / amount 等。"""
        return {}

    def parse(self, msg: EmailMessage, account_email: str, uid: str) -> InvoiceRecord:
        subject = msg.get("Subject", "")
        date_hdr = msg.get("Date", "")
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(date_hdr)
            invoice_date = dt.strftime("%Y-%m-%d") if dt else None
        except Exception:
            invoice_date = None

        record = InvoiceRecord(
            provider=self.name,
            account_email=account_email,
            uid=uid,
            invoice_date=invoice_date,
            subject=subject,
            documents=self.extract_attachments(msg),
        )
        record.extra.update(self.parse_subject(subject))
        # provider-specific override：把 invoice_number/amount 從 extra 拉到頂層
        if "invoice_number" in record.extra and not record.invoice_number:
            record.invoice_number = record.extra["invoice_number"]
        if "total_amount" in record.extra and not record.total_amount:
            record.total_amount = record.extra["total_amount"]
        return record


class DashboardProvider(BaseProvider):
    """信件僅含 link，需登入 dashboard 下載 — Uber-style。"""

    def parse(self, msg: EmailMessage, account_email: str, uid: str) -> InvoiceRecord:
        raise NotImplementedError("DashboardProvider 子類必須實作 parse()")
