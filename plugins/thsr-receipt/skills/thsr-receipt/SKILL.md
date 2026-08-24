---
name: thsr-receipt
description: 自動下載台灣高鐵購票證明 / 交易紀錄 PDF 用於報帳。當使用者說「下載高鐵購票證明」、「高鐵報帳」、「幫我抓高鐵車票」、貼出高鐵訂票成功 / T Express 票證資訊截圖、或紙本車票照片時觸發。也適用於使用者只丟訂位代號或紙票票號但上下文是出差 / 報帳的情境。支援 T Express 電子票（含對號座/自由座/統編戳章）與磁票/QR Code 紙票兩種來源。
---

# 台灣高鐵車票證明自動下載 — Claude 操作手冊

> 路徑說明：`{SKILL_DIR}` ＝ 本 skill 的安裝目錄（skill 載入時系統會標示 base directory；手動裝在 `~/.claude/skills/` 的話就是那裡，plugin 安裝則在 plugin 快取目錄）。


從 `ptis.thsrc.com.tw` 下載報帳 PDF，自動歸檔到 `~/Downloads/thsr_receipts/YYYY-MM/`，自動 qpdf 解密。
**這份檔案是寫給「執行這個 skill 的 Claude」看的，不是寫給最終使用者**。

---

## 核心知識：兩種票證走兩條路

| | T Express 電子票 | 磁票 / QR Code 紙票 |
|---|---|---|
| 來源 | T Express App 訂位後沒取紙本 | 訂票後到取票機/超商/窗口換紙本（含現場買）|
| 識別 | App 截圖（橘色 banner、有「下載電子車票證明」按鈕）| 紙票照片（有 `XX-X-XX-X-XXX-XXXX` 13 碼票號） |
| HSR 給的 PDF | **電子車票證明** — 報稅扣抵憑證 | **交易紀錄** — 帳務憑證 |
| 統編戳章 | ✅ 印 PDF 上 | ❌ 系統不提供 |
| 報稅扣抵 | ✅ | ❌（要去 HSR 窗口辦特殊憑證）|
| 重複下載 | ❌ 1 輩子 1 次 | ✅ 無限重複 |
| Skill 旗標 | `--ticket-type texpress`（預設）| `--ticket-type magnetic` |

**判斷流程**：
- 看到 App 截圖 → texpress
- 看到紙票照片 → magnetic
- 使用者說「現場買的」「超商買的」→ magnetic
- 使用者說「App 訂的」「還沒取票」→ texpress
- 不確定 → 問

---

## Phase 0：環境自我檢查

```bash
which python3   || echo "❌ 缺 python3 → brew install python"
which qpdf      || echo "⚠️ 缺 qpdf → brew install qpdf（沒裝會 fallback 顯示密碼）"
python3 -c "import playwright" 2>&1 | grep -q ModuleNotFoundError && \
  echo "❌ 缺 playwright → pip3 install --break-system-packages playwright && python3 -m playwright install chromium"
[ -f ~/.config/thsr-receipt/companies.json ] || \
  echo "📋 還沒有公司清單 → 第一次跑要建立"
```

---

## Phase 1：第一次設定（companies.json 不存在時）

**主動引導使用者建公司清單**，不要直接跑下載失敗。

問使用者：「你最常請款的公司有哪些？告訴我簡稱、統編、全名（或只給統編，我反查）。」

### 如果使用者只給統編（8 碼數字）

用經濟部 GCIS 公開 API 反查公司全名：

```bash
curl -sL "https://data.gcis.nat.gov.tw/od/data/api/5F64D864-61CB-4D0D-8AD9-492047CC1EA6?\$format=json&\$filter=Business_Accounting_NO%20eq%2012345678&\$top=5"
```

回應：
```json
[{"Business_Accounting_NO": "12345678", "Company_Name": "範例股份有限公司", ...}]
```

### 如果使用者貼 twincn URL

URL 格式 `https://twincn.com/item.aspx?no=XXXXXXXX`，從 `?no=` 抓 8 碼，同上 GCIS 反查。

### 寫入 companies.json

```bash
mkdir -p ~/.config/thsr-receipt
cat > ~/.config/thsr-receipt/companies.json <<'EOF'
[
  {"label": "簡稱", "tax_id": "12345678", "name": "全名股份有限公司"}
]
EOF
chmod 600 ~/.config/thsr-receipt/companies.json
```

驗證：
```bash
python3 {SKILL_DIR}/scripts/download.py --list
```

---

## Phase 2：解析輸入

### 圖片太大讀不了（HEIC、> 256KB）

```bash
sips -s format jpeg -s formatOptions 70 --resampleWidth 800 \
  "~/Downloads/IMG_XXXX.HEIC" --out "/tmp/IMG_XXXX.jpg"
```

### T Express App 截圖讀取重點

橘色 banner 「票證資訊」標題下：
- **訂位代號**（橘色字、8 碼數字，例 `12345678`）
- **車票號碼**（橘色字、13 碼數字，例 `2900000000000`）
- **乘車日期** + 時間（例 `2026/04/29` `07:00`）
- **起站 → 訖站**（例「南港 → 台中」）
- 行程類型：單程票 / 去回票
- 多人票或去回票會看到**多筆「成人」row**，每 row 一個 tid

### 紙本車票照片讀取重點

- 票面號碼 `XX-X-XX-X-XXX-XXXX`（**去掉 dash 變 13 碼，這就是 tid**）
- 日期 `YYYY/MM/DD`
- 路線 `XX → YY`
- 「自由座」標記 → `--seat-type free`

### 必要欄位 by 票種

| 票種 | 必要 |
|---|---|
| T Express 對號座 | pnr + tid + date + 公司 |
| T Express 自由座 | tid + date + 公司（無 pnr）|
| 磁票（任何座位） | tid + date + from + to（公司可省，無統編戳章）|

---

## Phase 3：問「請款給哪一家公司」

**每次都要問，不要假設用同一家**（使用者可能對多家公司請款）。

```bash
python3 {SKILL_DIR}/scripts/download.py --list
```

把清單列給使用者，問：「這次給哪家？」

使用者可能回：
- label（例「範例公司A」）→ `--company-label "範例公司A"`
- 一次性的統編 + 全名 → `--tax-id 12345678 --company "XX 股份有限公司"`
- 「同上次」→ 找前面的對話脈絡，不要硬猜

---

## Phase 4：執行下載

### T Express 對號座（最常見）
```bash
python3 {SKILL_DIR}/scripts/download.py \
  --pnr 12345678 --tid 2900000000000 \
  --date 2026-04-29 --from 南港 --to 台中 \
  --company-label "範例公司A"
```

### T Express 自由座
```bash
python3 {SKILL_DIR}/scripts/download.py \
  --tid 2900000000000 --date 2026-04-29 \
  --from 南港 --to 台中 \
  --seat-type free \
  --company-label "範例公司A"
```

### 磁票 / QR Code 紙票
```bash
python3 {SKILL_DIR}/scripts/download.py \
  --ticket-type magnetic --seat-type free \
  --tid 0710601010526 --date 2026-04-11 \
  --from 台中 --to 南港 \
  --company-label "範例公司A"
```

PDF 自動解密、依乘車日 YYYY-MM 分資料夾。

---

## 錯誤 cookbook

| 錯誤 | 真實原因（依機率排序）| 修法 |
|---|---|---|
| `請確認票卡資料正確性`（HSR modal）| 1. 日期格式被自作聰明 → 確認傳的是 `YYYY-MM-DD` 不是 `YYYY/MM/DD`<br>2. T Express 1 次限制已用掉<br>3. 訂位代號 / 車票號碼 / 日期不符 | 先驗格式，再用 headed mode 看實際畫面，最後問使用者是否曾下載過 |
| `找不到 tid=XXX 的下載按鈕` | 該 tid 已下載過，按鈕被 HSR 移除 | T Express 1 次限制，無法重抓 |
| `找不到 input#iUniNumber` | 走錯 path（磁票走 T Express 流程）| 確認 `--ticket-type` 對 |
| `'re.Pattern' object is not iterable` | select_option 用了 regex（已 fix）| 確認 download.py 是最新版 |
| 模 modal 沒跳出 | 磁票本來就沒 modal（直接下載）| 不是 bug，磁票 path 已經處理 |

---

## 重要的 quirk（會影響使用者決策）

1. **T Express 1 輩子 1 次** — 一旦下載就鎖定那個統編，無法改。誤下載要去 HSR 窗口辦。
2. **磁票無限重複** — 但 PDF 沒蓋統編戳章，多家公司可同時用同一張票（理論上）。
3. **去回票 / 分票 → 同 pnr 多 tid** — 每個 tid 獨立的 1 次下載額度。
4. **PDF 密碼 = 乘車日 YYYYMMDD** — qpdf 已經自動解了，使用者不用知道。

### 補救情境

**「我用錯統編下載了，能改嗎？」**
- 同一 tid 不行（HSR 永久鎖定）。
- 但若是去回票或分票，**回程 / 另一張票的 tid 還可下載** → 用那張補給另一家公司。範例：04/29 去程（tid 2900000000000）誤給範例公司A → 回程 tid 2900000000001 還能給豆樂逗樂。

**「磁票要報稅扣抵」**
- 線上拿不到。請使用者去 HSR 車站窗口辦特殊憑證。

---

## 不在範圍

| 別人問你 | 你回 |
|---|---|
| 回數票 / 定期票 | 走 HSR 另一個 tab，不是這個 skill |
| 高鐵電子發票（不一樣的東西）| 走 https://einvoice.nat.gov.tw |
| 台鐵車票 | 用姊妹 skill `tra-receipt` |
| 磁票要統編戳章 | HSR 系統限制，要去窗口辦特殊憑證 |
