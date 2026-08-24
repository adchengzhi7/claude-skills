"""Uber 收據 PDF → 結構化 JSON

從 Uber 收據 PDF 抽出報帳所需的所有欄位。容錯：欄位抓不到時填 None，不 fail。

Output JSON schema:
    {
      "trip_date": "2026-04-29",
      "trip_time_start": "12:38",
      "trip_time_end": "12:51",
      "from_address": "406台灣臺中市北屯區長生巷5-9號",
      "to_address": "414台灣臺中市烏日區站區一路(二樓大廳層)",
      "from_short": "北屯",
      "to_short": "烏日",
      "total": 482,
      "trip_fare": 472,
      "processing_fee": 10,
      "vehicle_plate": "ABC1234",
      "driver_license": "NA000001",
      "fleet": "計程車車隊名稱",
      "product": "UberX",
      "distance_km": 14.78,
      "duration_min": 12,
      "is_taxi": true,
      "is_refunded": false,
      "is_eats": false,
      "payment_method": "Apple Pay Mastercard ••••0000",
      "source_path": "/path/to/receipt.pdf"
    }
"""
from __future__ import annotations

import json
import re
import sys
import warnings
from pathlib import Path
from typing import Any

# pdfminer 的 FontBBox 警告蓋掉 stderr
warnings.filterwarnings("ignore")

import pdfplumber  # noqa: E402


# 全形數字 → 半形
_FW2HW = str.maketrans("０１２３４５６７８９", "0123456789")


def _normalize(text: str) -> str:
    return text.translate(_FW2HW)


def _extract_text(pdf_path: Path) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        pages = [p.extract_text() or "" for p in pdf.pages]
    return _normalize("\n".join(pages))


def _parse_date(text: str) -> str | None:
    m = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", text)
    if not m:
        return None
    y, mo, d = m.groups()
    return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"


def _to_24h(am_pm: str, hour: int, minute: int) -> str:
    if am_pm == "上午":
        h = 0 if hour == 12 else hour
    else:  # 下午
        h = hour if hour == 12 else hour + 12
    return f"{h:02d}:{minute:02d}"


def _parse_trip_times(text: str) -> tuple[str | None, str | None]:
    """從第二頁的「上下車地址」前的時間抓上車時間 + 下車時間。

    PDF 文字結構（第 2 頁）:
        下午 12:38
        406台灣臺中市北屯區長生巷5-9號
        下午 12:51
        414台灣臺中市烏日區站區一路(...)
    """
    times = re.findall(
        r"(上午|下午)\s*(\d{1,2}):(\d{2})\s*\n\s*\d{3,5}台灣",
        text,
    )
    if len(times) >= 2:
        start = _to_24h(times[0][0], int(times[0][1]), int(times[0][2]))
        end = _to_24h(times[1][0], int(times[1][1]), int(times[1][2]))
        return start, end
    if len(times) == 1:
        start = _to_24h(times[0][0], int(times[0][1]), int(times[0][2]))
        return start, None
    return None, None


def _parse_addresses(text: str) -> tuple[str | None, str | None]:
    """抓「下午 H:MM\n<3-5 碼郵遞區號>台灣...」裡的兩個地址。"""
    addrs = re.findall(r"\d{3,5}台灣[^\n]+", text)
    if len(addrs) >= 2:
        return addrs[0].strip(), addrs[1].strip()
    if len(addrs) == 1:
        return addrs[0].strip(), None
    return None, None


def _short_name(address: str | None) -> str | None:
    """從台灣地址抓「區」或「市」。

    優先順序：
    1. 高鐵站特徵（站區一路 / 烏日 高鐵）→ 加「高鐵」後綴
    2. 機場特徵 → 「松機」「桃機」「小港」
    3. 區名（XX區）
    4. 市名（XX市，無區的鄉鎮市）
    """
    if not address:
        return None

    # 高鐵站偵測
    if "站區一路" in address or "高鐵" in address:
        m_district = re.search(r"市([^區]+)區", address)
        if m_district:
            return f"{m_district.group(1)}高鐵"
        return "高鐵站"

    # 機場偵測
    if "松山機場" in address or "敦化北路405" in address:
        return "松機"
    if "桃園國際機場" in address or "大園" in address:
        return "桃機"
    if "小港機場" in address:
        return "小港"

    # 一般 → 區
    m = re.search(r"市([^區市]+)區", address)
    if m:
        return m.group(1).strip()
    m = re.search(r"縣([^鄉鎮市區]+)[鄉鎮市]", address)
    if m:
        return m.group(1).strip()
    return None


def _parse_money(text: str, label: str) -> int | None:
    m = re.search(rf"{re.escape(label)}\s*\$?([\d,]+)", text)
    if not m:
        m = re.search(rf"{re.escape(label)}[\s\n]*\$([\d,]+)", text)
    if not m:
        return None
    return int(m.group(1).replace(",", "").split(".")[0])


def _parse_total(text: str) -> int | None:
    """總計 $XXX.XX — 數字可能在下一行。"""
    m = re.search(r"總計\s*\n?\s*\$([\d,]+)", text)
    if not m:
        return None
    return int(m.group(1).replace(",", "").split(".")[0])


def _parse_plate(text: str) -> str | None:
    """車牌號碼後面（可能跨行 + 夾雜距離資訊）找 plate-like token。

    台灣車牌常見格式：ABC-1234 / ABC1234 / 1234-AB / AB-1234。
    """
    plate_pat = r"[A-Z]{2,3}-?\d{3,4}|\d{3,4}-?[A-Z]{2,3}"
    m = re.search(
        rf"車牌號碼[：:][\s\S]{{0,120}}?\b({plate_pat})\b",
        text,
    )
    return m.group(1) if m else None


def _parse_license(text: str) -> str | None:
    m = re.search(r"駕駛執業登記證證號[：:]\s*([A-Z0-9\-]+)", text)
    return m.group(1) if m else None


def _parse_fleet(text: str) -> str | None:
    m = re.search(r"車行[／/]車隊[：:]\s*([^\n]+)", text)
    return m.group(1).strip() if m else None


def _parse_product(text: str) -> str | None:
    """第二頁「行程詳細資訊」下一行就是產品名稱。"""
    m = re.search(r"行程詳細資訊\s*\n\s*([^\n\s車]+)", text)
    if m:
        return m.group(1).strip()
    # fallback: 找常見 product 字樣
    for p in ["UberX", "Premier", "Comfort", "Uber Black", "UberTAXI", "Uber Taxi", "Green", "Pet"]:
        if p in text:
            return p
    return None


def _parse_distance(text: str) -> tuple[float | None, int | None]:
    m = re.search(r"([\d.]+)\s*公里[,，]\s*(\d+)\s*minutes?", text)
    if m:
        return float(m.group(1)), int(m.group(2))
    return None, None


def _parse_payment(text: str) -> str | None:
    m = re.search(r"款項\s*\n([^\n]+\$[\d,]+\.?\d*)", text)
    if m:
        line = m.group(1).strip()
        line = re.sub(r"\s*\$[\d,]+\.?\d*\s*$", "", line)
        return line.strip()
    return None


def _is_eats(text: str) -> bool:
    # 不能只看有沒有「Uber Eats」字樣：Uber 會在「行程」收據信裡夾帶 Uber Eats
    # 廣告（例：「在 Uber Eats 享受比賽日優惠／訂購漢堡、披薩」），用它當關鍵字
    # 會把正常的商務行程誤判成外送而丟掉。改用只有外送訂單才會出現的特徵。
    return any(kw in text for kw in
               ["送出的訂單", "訂單編號", "您的訂單", "餐廳合作", "外送費", "外送員"])


def _is_refunded(text: str) -> bool:
    return any(kw in text for kw in ["已退款", "Refunded", "退款金額", "已取消"])


def parse_text(text: str, *, source_path: str | None = None) -> dict[str, Any]:
    """從已抽出的純文字（PDF 或 email HTML 剝乾淨後）解析欄位。"""
    text = _normalize(text)

    if _is_eats(text):
        return {
            "source_path": source_path,
            "is_eats": True,
            "error": "這是 Uber Eats 的收據，不是行程收據（uber-receipt 不處理外送）",
        }

    from_addr, to_addr = _parse_addresses(text)
    start_time, end_time = _parse_trip_times(text)
    license_num = _parse_license(text)

    return {
        "trip_date": _parse_date(text),
        "trip_time_start": start_time,
        "trip_time_end": end_time,
        "from_address": from_addr,
        "to_address": to_addr,
        "from_short": _short_name(from_addr),
        "to_short": _short_name(to_addr),
        "total": _parse_total(text),
        "trip_fare": _parse_money(text, "行程費用"),
        "processing_fee": _parse_money(text, "Uber處理費"),
        "vehicle_plate": _parse_plate(text),
        "driver_license": license_num,
        "fleet": _parse_fleet(text),
        "product": _parse_product(text),
        "distance_km": _parse_distance(text)[0],
        "duration_min": _parse_distance(text)[1],
        "is_taxi": bool(license_num),
        "is_refunded": _is_refunded(text),
        "is_eats": False,
        "payment_method": _parse_payment(text),
        "source_path": source_path,
    }


def parse_pdf(pdf_path: str | Path) -> dict[str, Any]:
    pdf_path = Path(pdf_path).expanduser().resolve()
    text = _extract_text(pdf_path)
    return parse_text(text, source_path=str(pdf_path))


def main():
    if len(sys.argv) < 2:
        print("用法: python3 parse.py <pdf-path>", file=sys.stderr)
        sys.exit(1)

    result = parse_pdf(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
