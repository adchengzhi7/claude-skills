---
name: thsr-receipt
description: 自動下載台灣高鐵購票證明 / 交易紀錄 PDF 用於報帳。當使用者說「下載高鐵購票證明」、「高鐵報帳」、「幫我抓高鐵車票」、貼出高鐵訂票成功 / 取票畫面截圖、或同時提供高鐵訂位代號（8 碼數字）+ 乘車日 + 起訖站時觸發。也適用於使用者只丟訂位代號但上下文是出差 / 報帳的情境。支援 T Express 電子票與磁票/QR Code 紙票兩種來源。
---

# 台灣高鐵車票證明自動下載

從 `ptis.thsrc.com.tw` 下載報帳 PDF，自動命名歸檔到 `~/Downloads/thsr_receipts/`，自動 qpdf 解密。

## 兩種票證、兩種文件、兩種限制

| | T Express 電子票 | 磁票 / QR Code 紙票 |
|---|---|---|
| 來源 | T Express App 訂的、未取紙本 | 網站訂位後到車站取票機 / 超商 / 窗口取得紙本（包含現場購買）|
| HSR 給的 PDF | **電子車票證明**（報稅扣抵憑證）| **交易紀錄**（帳務憑證）|
| 統編戳章 | ✅ 有 | ❌ 沒有（HSR 系統不提供）|
| 報稅扣抵 | ✅ 可 | ❌ 不可（要去窗口辦）|
| 公司帳務憑證 | ✅ | ✅（多數公司接受）|
| 重複下載 | ❌ 1 輩子 1 次 | ✅ 可無限重複 |
| Skill 旗標 | `--ticket-type texpress`（預設）| `--ticket-type magnetic` |

## 觸發判斷

- 使用者說「下載高鐵購票證明」、「高鐵 receipt」、「報帳要的高鐵車票」
- 使用者貼出高鐵訂票確認 / 取票成功畫面截圖（T Express App 內）
- 使用者貼出高鐵紙本車票照片（磁票 / QR Code 紙票）
- 使用者同時提供：訂位代號（8 碼）+ 車票號碼（13 碼）+ 乘車日 + 起訖站

## 必要資訊

### T Express 對號座
- 訂位代號（8 碼數字）
- 車票號碼（13 碼數字，去回票或多人票任選一張）
- 搭乘日期 YYYY-MM-DD
- 起站 / 訖站（中文站名）

### T Express 自由座
- 車票號碼（13 碼數字）
- 搭乘日期 YYYY-MM-DD
- ⚠️ 不需要訂位代號

### 磁票 / QR Code 紙票（任意座位）
- 車票號碼（13 碼數字，紙票面 `XX-X-XX-X-XXX-XXXX` 去掉 dash）
- 搭乘日期 YYYY-MM-DD
- 起站 / 訖站（中文站名）

### 報帳資訊（T Express 必填，磁票會被忽略）
- 統一編號（8 碼數字）
- 營利事業名稱

## 重要：每次都要問使用者「請款給哪一家公司」

使用者可能對多家公司請款（自己的、客戶的、僱主的）。**不要假設用同一家**。

### 觸發後的標準流程

1. **先列出可選公司**：
   ```bash
   python3 ~/.claude/skills/thsr-receipt/scripts/download.py --list
   ```

2. **問使用者**：「這次要請款給哪一家？」（即使是磁票也問，雖然 PDF 不會印統編，但記錄用）
   - 回答 label（例：「台積電」）
   - 或一次性給 `--tax-id` + `--company`

3. **跑下載**：

   T Express（預設）：
   ```bash
   python3 ~/.claude/skills/thsr-receipt/scripts/download.py \
     --pnr 87654321 \
     --tid 1234567890123 \
     --date 2026-04-29 \
     --from 南港 --to 台中 \
     --company-label "台積電"
   ```

   T Express 自由座（無 pnr）：
   ```bash
   python3 ~/.claude/skills/thsr-receipt/scripts/download.py \
     --tid 1234567890123 \
     --date 2026-04-29 \
     --from 南港 --to 台中 \
     --seat-type free \
     --company-label "台積電"
   ```

   磁票 / QR Code 紙票：
   ```bash
   python3 ~/.claude/skills/thsr-receipt/scripts/download.py \
     --ticket-type magnetic \
     --seat-type free \
     --tid 9999999999992 \
     --date 2026-04-11 \
     --from 台中 --to 南港 \
     --company-label "台積電"
   ```

### 公司清單檔案結構

`~/.config/thsr-receipt/companies.json`（**本機獨有，永遠不上 git**）：

```json
[
  {"label": "台積電", "tax_id": "22099131", "name": "台灣積體電路製造股份有限公司"}
]
```

如果使用者還沒建這個檔案，**第一次觸發時要引導他建立**。

## CLI 旗標

| 旗標 | 說明 |
|---|---|
| `--ticket-type` | `texpress`（預設）/ `magnetic` |
| `--seat-type` | `reserved`（對號座，預設）/ `free`（自由座）|
| `--pnr` | 訂位代號 8 碼（T Express 對號座必填，自由座/磁票可省）|
| `--tid` | 車票號碼 13 碼（必填）|
| `--date` | 搭乘日期 YYYY-MM-DD（必填）|
| `--from` / `--to` | 中文站名（磁票必填、T Express 僅用於檔名）|
| `--tax-id` / `--company` | 統編 / 公司名（T Express 必填，磁票會無視）|
| `--company-label` | 從 companies.json 挑（更方便）|
| `--list` | 列出可選公司 |

合法車站：南港 / 台北 / 板橋 / 桃園 / 新竹 / 苗栗 / 台中 / 彰化 / 雲林 / 嘉義 / 台南 / 左營

## PDF 處理

- 下載後 PDF 有密碼保護（密碼 = 乘車日 YYYYMMDD）
- 腳本自動用 `qpdf` 解密（前提：`brew install qpdf`），檔案直接打開不用密碼
- 沒裝 qpdf 會 fallback 顯示密碼讓使用者手動輸入
- 檔名：`{乘車日}-{起站}-{訖站}-{tid}.pdf`，落在 `~/Downloads/thsr_receipts/`

## 限制與規定（HSR 官方）

- T Express 電子車票證明：**1 輩子 1 次下載**，遺失或誤下載要去 HSR 窗口辦
- T Express 可查發車日 + 2 日起 ~ 5 年內
- 磁票交易紀錄：可查前一年到前一日
- 票價為 0 的票無法提供
- 自由座車票只能用「車票號碼」查詢，不能用「訂位代號」

## 不在範圍內

- 回數票 / 定期票 → 走另一個系統 tab
- 高鐵電子發票 → 走 https://einvoice.nat.gov.tw
- 多家公司同行的分票多 leg 報帳 → 各自跑一次（每張 tid 獨立）
