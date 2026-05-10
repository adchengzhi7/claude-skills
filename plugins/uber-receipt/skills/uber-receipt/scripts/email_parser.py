"""從 Uber 行程 email HTML 直接解析行程資料（不需 PDF）。

設計理由：
    Uber 信件的 HTML body 已含完整收據資料（金額、起訖、車牌、車隊、駕駛證），
    且信件內所有 PDF 下載連結都需要登入 riders.uber.com（click-tracker）。
    所以最可靠的自動化路徑是：直接 parse email HTML，不去抓 PDF。
    保留 .eml 原檔當作報帳憑證。

對應 parse.py 的 schema，可無縫接 organize / report。
"""
from __future__ import annotations

import email
import email.policy
import re
import sys
from email.message import EmailMessage
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from parse import parse_text  # noqa: E402


def _strip_html(html: str) -> str:
    """HTML → 類 PDF 純文字。

    保留 td/tr 邊界（用 `\n` 分隔）讓「label: value」這種跨 td 的結構正確相鄰。
    """
    text = html
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL)
    text = re.sub(r"</td>", "\n", text)
    text = re.sub(r"</tr>", "\n", text)
    text = re.sub(r"<br[^>]*>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text


def _extract_html_from_msg(msg: EmailMessage) -> str:
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
    elif msg.get_content_type() == "text/html":
        try:
            return msg.get_content()
        except Exception:
            return ""
    return ""


def parse_email(msg: EmailMessage, *, eml_source_path: str | None = None) -> dict[str, Any]:
    """從 Uber email message 解析出 trip dict（與 parse_pdf 同 schema）。

    eml_source_path 是這封 email 將會儲存的 .eml 路徑（給 organize 用）。
    """
    html = _extract_html_from_msg(msg)
    if not html:
        return {
            "source_path": eml_source_path,
            "is_eats": False,
            "error": "email 沒有 HTML body，無法解析",
        }

    text = _strip_html(html)
    trip = parse_text(text, source_path=eml_source_path)
    trip["_email_html"] = html
    trip["_email_subject"] = msg.get("Subject", "")
    trip["_email_date"] = msg.get("Date", "")
    return trip


def save_eml(msg: EmailMessage, target_path: Path) -> None:
    """把 EmailMessage 序列化成 .eml 檔案（標準 RFC 5322 格式）。"""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(msg.as_bytes())


def parse_eml_file(eml_path: str | Path) -> dict[str, Any]:
    """讀已歸檔的 .eml 檔重新 parse — 給 report.py 重新跑時用。"""
    eml_path = Path(eml_path).expanduser().resolve()
    raw = eml_path.read_bytes()
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    return parse_email(msg, eml_source_path=str(eml_path))


def extract_receipt_tracker(html: str) -> str | None:
    """抓信件「下載 Uber 電子明細 PDF」按鈕的 click-tracker URL。

    fallback：找「請造訪行程頁面」的 link（trip page，非直接下載）。
    用 Playwright 跟隨後可取得 trip UUID + 直接下載 PDF。
    """
    if not html:
        return None
    # 「下載 Uber 電子明細 PDF」按鈕 — 文字在 td 內，wrapper 是 <a>
    idx = html.find("下載 Uber 電子明細 PDF")
    if idx == -1:
        idx = html.find("Download Uber Trip Receipt PDF")  # 英文 fallback
    if idx != -1:
        m_list = list(re.finditer(r'<a[^>]+href="([^"]+)"', html[:idx]))
        if m_list:
            return m_list[-1].group(1)

    # fallback：「請造訪行程頁面」
    m = re.search(r'<a[^>]+href="([^"]+)"[^>]*>[^<]*請造訪行程頁面', html)
    if m:
        return m.group(1)
    return None


def parse_xml_invoice(xml_path: str | Path) -> dict[str, Any]:
    """讀 MIG 3.2 統一發票 XML，抽出 發票號碼/日期/賣方/買方。"""
    import xml.etree.ElementTree as ET

    xml_path = Path(xml_path).expanduser().resolve()
    tree = ET.parse(xml_path)
    root = tree.getroot()
    ns = {"inv": "urn:GEINV:eInvoiceMessage:C0401:3.2"}

    def text(path):
        el = root.find(path, ns)
        return el.text if el is not None else None

    return {
        "invoice_number": text(".//inv:InvoiceNumber"),
        "invoice_date": text(".//inv:InvoiceDate"),
        "invoice_time": text(".//inv:InvoiceTime"),
        "seller_id": text(".//inv:Seller/inv:Identifier"),
        "seller_name": text(".//inv:Seller/inv:Name"),
        "buyer_id": text(".//inv:Buyer/inv:Identifier"),
        "buyer_name": text(".//inv:Buyer/inv:Name"),
        "total_amount": text(".//inv:TotalAmount"),
        "tax_amount": text(".//inv:TaxAmount"),
        "xml_path": str(xml_path),
    }
