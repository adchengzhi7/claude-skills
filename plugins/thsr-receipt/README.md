# thsr-receipt

自動下載**台灣高鐵**購票證明 / 交易紀錄 PDF 用於報帳，做成 [Claude Code](https://claude.com/claude-code) Skill / Plugin。

> 姊妹專案：[tra-receipt](../tra-receipt/)（台鐵）

## 它做什麼

在 Claude Code 裡丟一句：

```
下載高鐵購票證明：訂位代號 87654321，2026/04/29 南港→台中
```

或拖一張高鐵訂票確認 / T Express 票證資訊截圖、或紙本車票照片進來，PDF 自動落地：

```
~/Downloads/thsr_receipts/2026-04-29-南港-台中-1234567890123.pdf
```

**自動 qpdf 解密、檔名用車票號碼結尾、自動依 PDF 內容辨識**。

## ⚡ 兩種票證、兩種文件、兩種限制（必讀）

HSR 把車票分兩種，這兩種**走不同 URL、不同 API、產出不同 PDF**：

| | T Express 電子票 | 磁票 / QR Code 紙票 |
|---|---|---|
| **來源** | T Express App 訂位後直接走 | 訂票 → 取票機/超商/窗口換紙本（含現場購買）|
| **HSR 給的 PDF** | **電子車票證明**（報稅扣抵憑證）| **交易紀錄**（帳務憑證）|
| **統編戳章** | ✅ 印在 PDF 上 | ❌ HSR 系統不提供 |
| **報稅扣抵效力** | ✅ 財政部核定憑證 | ❌ 不可（要去 HSR 窗口辦特殊憑證）|
| **公司帳務憑證** | ✅ | ✅（多數公司可接受）|
| **重複下載** | ❌ 1 輩子 1 次 | ✅ 可無限重複 |
| **本 skill 旗標** | `--ticket-type texpress`（預設）| `--ticket-type magnetic` |

**白話**：紙票（磁票）只能拿到「沒蓋統編的交易紀錄」，給公司走帳通常 OK，但報稅抵稅不行。要報稅抵稅必須是 T Express 電子票。

## 跟台鐵的差別

| 項目 | 台鐵 (tra-receipt) | 高鐵 (thsr-receipt) |
|---|---|---|
| 認證方式 | 身分證 + 訂票代碼 | 訂位代號 + 車票號碼（不需身分證）|
| 統編 / 公司 | ❌ 不適用 | ✅ T Express 必填、磁票無視 |
| PDF 加密 | ❌ | ✅ 密碼 = 乘車日 YYYYMMDD（自動解密）|
| 下載次數 | 無限 | T Express 1 次、磁票無限 |

## 安裝

走 marketplace（推薦）：

```
/plugin marketplace add adchengzhi7/claude-skills
/plugin install thsr-receipt
```

依賴：`brew install qpdf` （自動解密用）+ `pip3 install --break-system-packages playwright` + `python3 -m playwright install chromium`

## CLI 用法

### T Express 對號座（預設情境）

```bash
python3 ~/.claude/skills/thsr-receipt/scripts/download.py \
  --pnr 87654321 \
  --tid 1234567890123 \
  --date 2026-04-29 \
  --from 南港 --to 台中 \
  --company-label "台積電"
```

### T Express 自由座（無訂位代號）

```bash
python3 ~/.claude/skills/thsr-receipt/scripts/download.py \
  --tid 1234567890123 \
  --date 2026-04-29 \
  --from 南港 --to 台中 \
  --seat-type free \
  --company-label "台積電"
```

### 磁票 / QR Code 紙票（現場/超商買的）

紙票面寫的票號是 `XX-X-XX-X-XXX-XXXX` 格式，去掉 dash 連起來即 13 碼：

```bash
python3 ~/.claude/skills/thsr-receipt/scripts/download.py \
  --ticket-type magnetic \
  --seat-type free \
  --tid 9999999999992 \
  --date 2026-04-11 \
  --from 台中 --to 南港 \
  --company-label "台積電"
```

> 磁票會無視 `--tax-id` / `--company-label`，因為 PDF 不蓋統編戳章 — 但仍建議帶著，紀錄哪張票報給哪家。

## 旗標

| 旗標 | 說明 |
|---|---|
| `--ticket-type` | `texpress`（預設）/ `magnetic` |
| `--seat-type` | `reserved`（對號座，預設）/ `free`（自由座）|
| `--pnr` | 訂位代號 8 碼（T Express 對號座必填）|
| `--tid` | 車票號碼 13 碼（必填）|
| `--date` | 搭乘日期 YYYY-MM-DD（必填）|
| `--from` / `--to` | 中文站名（磁票必填）|
| `--tax-id` / `--company` | 直接給統編 / 公司名 |
| `--company-label` | 從 `~/.config/thsr-receipt/companies.json` 挑 |
| `--list` | 列出可選公司 |

合法車站（中文）：南港 / 台北 / 板橋 / 桃園 / 新竹 / 苗栗 / 台中 / 彰化 / 雲林 / 嘉義 / 台南 / 左營

## 多公司清單系統

`~/.config/thsr-receipt/companies.json`（**永遠不上 git，存在你 Mac 上 chmod 600**）：

```json
[
  {"label": "台積電", "tax_id": "22099131", "name": "台灣積體電路製造股份有限公司"},
  {"label": "鴻海", "tax_id": "04541302", "name": "鴻海精密工業股份有限公司"}
]
```

> ⚠️ 上面台積電 / 鴻海是**公開公司範例**（這份 repo 用它們示範格式，你不用真的開單給他們）。**請替換成你自己常請款的公司**。 不知道某家統編？告訴 Claude 那家公司名 + 「幫我加進公司清單」，它會用經濟部 GCIS API 反查。

之後 `--company-label "台積電"` 即可。每次 Claude 觸發 skill 都會主動列清單問你「這次請款給哪家」，不會假設用同一家。

## PDF 密碼

下載後 PDF 加密、密碼 = 乘車日 YYYYMMDD（例：`20260429`）。**腳本自動 qpdf 解密**，檔案直接打開不用密碼。

如果沒裝 qpdf，會 fallback 顯示密碼讓你手動輸入。

## 隱私與安全

- 不需要身分證字號（跟台鐵不同）
- 訂位代號 / 車票號碼 / 統編 **不寫入任何 git track 的檔案**（公司清單在 `~/.config/`，gitignore 雙重保險）
- 連線都走 TLS，HSR 官方系統 `ptis.thsrc.com.tw`
- PDF 落本機 `~/Downloads/thsr_receipts/`，不上雲

## 限制（HSR 官方規定）

- T Express 電子車票證明：**1 輩子 1 次**，誤下載要去窗口辦
- T Express 可查發車日 + 2 日起 ~ 5 年內
- 磁票交易紀錄：可查前一年到前一日
- 票價為 0 的票無法提供
- 自由座票只能用「車票號碼」查、不能用「訂位代號」

## 不在範圍內

- 回數票 / 定期票 → 走另一個 tab
- 高鐵電子發票 → https://einvoice.nat.gov.tw
- 報稅扣抵憑證（磁票版）→ 必須去 HSR 窗口辦

## License

MIT — 同 root [LICENSE](../../LICENSE)
