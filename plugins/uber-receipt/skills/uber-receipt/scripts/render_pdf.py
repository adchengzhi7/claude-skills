"""把 Uber 收據 email 的 HTML body 渲染成 PDF。

用 Chromium headless 渲染，等同瀏覽器「列印 → 儲存為 PDF」。輸出視覺上接近
原始 Uber 收據（有 logo、地圖、明細）— 因為我們渲染的是同一份 HTML。

依賴：playwright（thsr-receipt 已裝）。
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("❌ 缺 playwright → pip3 install --break-system-packages playwright && python3 -m playwright install chromium", file=sys.stderr)
    raise


def html_to_pdf(html: str, output_path: Path | str, *, wait_for_images: bool = True) -> Path:
    """把 HTML 字串渲染成 PDF。

    wait_for_images=True 時用 networkidle 等所有 image / font 載入；False 用 load 比較快。
    """
    output_path = Path(output_path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    wait_state = "networkidle" if wait_for_images else "load"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            ctx = browser.new_context()
            page = ctx.new_page()
            page.set_content(html, wait_until=wait_state, timeout=20000)
            page.pdf(
                path=str(output_path),
                format="A4",
                margin={"top": "15mm", "right": "10mm", "bottom": "15mm", "left": "10mm"},
                print_background=True,
            )
        finally:
            browser.close()
    return output_path


def eml_to_pdf(eml_path: Path | str, output_path: Path | str | None = None) -> Path:
    """讀 .eml 檔、抽 HTML body、印成 PDF。"""
    import email
    import email.policy

    eml_path = Path(eml_path).expanduser().resolve()
    raw = eml_path.read_bytes()
    msg = email.message_from_bytes(raw, policy=email.policy.default)

    sys.path.insert(0, str(Path(__file__).parent))
    from email_parser import _extract_html_from_msg

    html = _extract_html_from_msg(msg)
    if not html:
        raise ValueError(f"{eml_path} 沒有 HTML body")

    if output_path is None:
        output_path = eml_path.with_suffix(".pdf")
    return html_to_pdf(html, output_path)


def main():
    import argparse
    p = argparse.ArgumentParser(description="Uber email .eml → PDF")
    p.add_argument("eml", help=".eml 檔路徑")
    p.add_argument("-o", "--output", help="輸出 PDF 路徑，預設同目錄同名 .pdf")
    args = p.parse_args()

    out = eml_to_pdf(args.eml, args.output)
    print(f"✅ 已輸出 PDF：{out}")


if __name__ == "__main__":
    main()
