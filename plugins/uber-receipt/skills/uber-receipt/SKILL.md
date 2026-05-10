---
name: uber-receipt
description: 整理 Uber 行程 PDF 收據用於報帳。當使用者說「整理 Uber 收據」「Uber 報帳」「處理本月 Uber」、提供 receipt_*.pdf 檔案路徑或一個含多張 Uber PDF 的資料夾時觸發。會解析 PDF、智慧建議分配公司（含同日連續行程偵測、跨 skill 高鐵綁定、私人行程啟發式判斷）、重命名歸檔、產生月份 summary.csv + summary.md。和姊妹 skill thsr-receipt / tra-receipt 共用 ~/.config/receipts/companies.json。
---

# Uber 收據整理 — Claude 操作手冊

把 Uber 行程 PDF（從 email 下載或 riders.uber.com 下載）解析、智慧分配公司、歸檔到 `~/Downloads/uber_receipts/YYYY-MM/`，產月報。**這份檔案是寫給「執行這個 skill 的 Claude」看的**，不是寫給最終使用者。

---

## 核心知識：和 thsr-receipt 不一樣

| | thsr-receipt | uber-receipt |
|---|---|---|
| 工作模式 | 從 HSR 網站「下載」PDF | PDF 已存在，「整理」既有 PDF |
| 自動化點 | Playwright 登入 + 表單 | pdfplumber 解析 + 重命名 |
| Companies | 用來填表（蓋統編戳章） | 純標籤（檔名 tag）|
| 報稅扣抵 | T Express 可以（要打統編） | 計程車車資**不行**，僅 $10 處理費可 |

**重要：Uber 在台灣是多元計程車模式**：
- 行程費用 → 計程車收，**Uber 不開營業人發票**
- Uber 處理費（通常 $10-30）→ Uber Formosa Co. Ltd. 開電子發票，**這部分才能改統編**
- PDF 上會有 `駕駛執業登記證證號` → 確認是計程車行程

整理 PDF 不會解決報稅問題；只是讓檔案乾淨、報帳明細容易交。

---

## Phase 0：環境檢查

```bash
which python3 || echo "❌ 缺 python3 → brew install python"
python3 -c "import pdfplumber" 2>&1 | grep -q ModuleNotFoundError && \
  echo "❌ 缺 pdfplumber → pip3 install --break-system-packages pdfplumber"
python3 ~/.claude/skills/uber-receipt/scripts/companies.py
# 沒公司清單 → 走 Phase 1

# Gmail 自動抓功能（可選但強烈推薦，不裝 fallback 是手動拖 PDF）
python3 ~/.claude/skills/uber-receipt/scripts/gmail_fetcher.py --check
# ❌ → 走 Phase 1.5
```

## Phase 1.5：Gmail 自動抓設定（可選）

如果使用者要全自動模式（不用每次手動下載 PDF），引導他做這三步：

**步驟 1：開 Gmail 2FA**（如果還沒開）
→ https://myaccount.google.com/security

**步驟 2：建 App Password**
→ https://myaccount.google.com/apppasswords
- App name: 填 `uber-receipt`
- 複製產生的 16 碼密碼（格式 `xxxx xxxx xxxx xxxx`）

**步驟 3：存進系統 — 給使用者一鍵指令（替換 EMAIL 和 PASSWORD）**

```bash
# 設定 email
python3 -c "
import sys
sys.path.insert(0, '$HOME/.claude/skills/uber-receipt/scripts')
from gmail_fetcher import save_gmail_email
save_gmail_email('YOUR_EMAIL@gmail.com')
"

# 存 App Password 到 macOS Keychain（安全儲存）
security add-generic-password \
  -a 'YOUR_EMAIL@gmail.com' \
  -s 'uber-receipt-gmail' \
  -w 'XXXX XXXX XXXX XXXX'
```

驗證：
```bash
python3 ~/.claude/skills/uber-receipt/scripts/gmail_fetcher.py --check
# ✅ Gmail 設定 OK：YOUR_EMAIL@gmail.com
```

**安全注意**：
- App Password 等同於該服務的密碼，請當成密碼保護（已存 Keychain，比明文好）
- 朋友 / 家人共用 Mac → 不要存，每次手動 export 環境變數即可
- 公司 Workspace 帳號的 admin 可能禁用 App Password → 那就只能 fallback 手動下載

## Phase 1.6：使用 --from-gmail 全自動模式

設定好之後，使用者只要說「整理本月 Uber」，跑：

```bash
python3 ~/.claude/skills/uber-receipt/scripts/main.py --from-gmail \
  --default-company 我的公司 \
  --json
```

→ 自動 IMAP 抓信、下載 PDF、解析、套啟發式建議。然後你（Claude）逐筆問使用者確認分配。

**已處理紀錄**：`~/.config/receipts/uber-processed.json` 會記錄每封已處理的 IMAP UID，下次不重抓。要強制重抓加 `--refetch`。

---

## Phase 1：第一次設定（companies.json 不存在時）

如果 `python3 .../companies.py` 顯示「需要建立公司清單」，引導使用者：

問：「你最常請款的公司有哪些？告訴我簡稱、統編、全名（或只給統編，我反查）。」

統編反查（GCIS）：
```bash
curl -sL "https://data.gcis.nat.gov.tw/od/data/api/5F64D864-61CB-4D0D-8AD9-492047CC1EA6?\$format=json&\$filter=Business_Accounting_NO%20eq%20<TAX_ID>&\$top=5"
```

寫入 `~/.config/receipts/companies.json`：
```bash
python3 -c "
import sys, json
sys.path.insert(0, '/Users/$USER/.claude/skills/uber-receipt/scripts')
from companies import write_companies
write_companies([
  {'label': '簡稱', 'tax_id': '12345678', 'name': '全名股份有限公司'},
])
"
```

**注意 legacy 自動 migration**：如果 `~/.config/thsr-receipt/companies.json` 已存在，第一次跑 `companies.py` 會自動複製過去，不需手動處理。

---

## Phase 2：解析輸入

使用者會給三種輸入之一：

### 形式 A：單一 PDF 路徑
```
'/path/to/receipt_xxx.pdf'
```
→ 跑 `--single`，問使用者要給哪家公司，做完。

### 形式 B：資料夾路徑（多張 PDF）
```
'/Users/xxx/Downloads/' 處理本月 Uber
```
→ 跑 `--batch --json` 把建議表抓進來，**逐筆**列給使用者確認，每張呼叫 `--single`。

### 形式 C：模糊指令
```
"幫我整理 4 月的 Uber 收據"
```
→ 主動掃 `~/Downloads/`、`~/Downloads/uber_receipts/2026-04/` 內未分類的 PDF（檔名沒 `[公司]` tag）。

---

## Phase 3：問 default 公司

在 `--batch` 之前，先跟使用者確認**這批的預設公司**：

```bash
python3 ~/.claude/skills/uber-receipt/scripts/main.py --list
```

問：「這批 Uber 主要報給哪家公司？」（可能會有少數例外，但設預設能讓啟發式更準）

---

## Phase 4：批次互動分配

```bash
python3 ~/.claude/skills/uber-receipt/scripts/main.py \
  --batch '/Users/xxx/Downloads/' \
  --default-company 我的公司 \
  --json
```

JSON 出來後，**用 markdown table 列給使用者**：

```
| # | 日期 時間 | 路線 | 金額 | 建議 | 原因 |
|---|---|---|---|---|---|
| 1 | 04-29 12:38 | 北屯 → 烏日高鐵 | $482 | 我的公司 | 預設 |
| 2 | 04-29 18:12 | 烏日高鐵 → 內湖 | $650 | 我的公司 | 同日連續行程 |
| 3 | 04-30 23:42 | 信義 → 大安 | $180 | 私人 | 啟發式（深夜+短途）|
```

問使用者：「全部照建議？還是要改某幾個？」

接受的回應形式：
- 「都好」「ok」 → 全部照建議
- 「3 改成我的公司」「3 不是私人是我的公司」 → 個別調整
- 「全部給第二家公司」 → 全改一家

### 執行歸檔

對每張 PDF 呼叫：
```bash
python3 ~/.claude/skills/uber-receipt/scripts/main.py \
  --single '/path/to/receipt_xxx.pdf' \
  --company-label 我的公司
```

或私人：
```bash
python3 .../main.py --single '/path/to/...pdf' --personal
```

---

## Phase 5：產月報

歸檔完跑：
```bash
python3 ~/.claude/skills/uber-receipt/scripts/main.py --report 2026-04
```

→ 產 `~/Downloads/uber_receipts/2026-04/summary.csv` 和 `summary.md`

跟使用者報告：
- 總趟數 / 總金額
- 每家公司分別多少
- 私人行程已排除幾趟（不含在 summary）

---

## 啟發式建議規則（classify.py 內邏輯，這裡只是參考）

| 規則 | 觸發 |
|---|---|
| 退款 | PDF 含「退款」「Refunded」 → 不分配，歸 _refunded/ |
| 同日連續 | 同日有別趟已分配 + 時差 ≤ 4 hr → 沿用 |
| 接駁高鐵 | 起/訖含「高鐵」+ 同日 thsr-receipt 有票 → 沿用那票公司 |
| 歷史路線 | 過去 90 天同 from-to ≥ 3 次同公司 → 沿用 |
| 私人候選 | 深夜（22-06）+ 週末 + 短途（< $100）三選二 → 「私人」|
| 都不符 | 用 `--default-company` |

**重要**：建議是建議，最終以使用者確認為準。任何啟發式判斷都要在 reason 欄位明確寫出，不要藏。

---

## 錯誤 cookbook

| 錯誤 / 狀況 | 真實原因 | 修法 |
|---|---|---|
| `error: 這是 Uber Eats 的收據` | 使用者把外送收據丟進來 | 略過，提示 uber-receipt 不處理外送 |
| `vehicle_plate: null` | PDF 排版讓車牌抓不到 | 檢查是否舊版 parse.py（plate regex 應跨行）|
| 解析欄位都是 null | PDF 結構變了 / 不是 Uber receipt | 跑 `--inspect` 印 raw text 給使用者看 |
| 批次掃不到 PDF | 檔名不是 `receipt_*.pdf`（使用者改名過）| 改用單檔模式逐張處理 |
| `Gmail 登入失敗 [AUTHENTICATIONFAILED]` | App Password 錯了 或 2FA 沒開 | 重新建 App Password、`security add-generic-password` 重存 |
| `Gmail 登入失敗 [LIMIT]` | 短時間 IMAP 失敗太多次，Google 暫鎖 | 等 30 分鐘 / 用 https://accounts.google.com/DisplayUnlockCaptcha 解鎖 |
| `--from-gmail` 抓到信但 `no_pdf` | Uber 信件 HTML 內 download link 需要登入 | fallback 請使用者點信件「下載收據」按鈕，再用 `--batch` 處理下載資料夾 |
| `--from-gmail` 抓 0 封 | 過濾條件抓不到 | 確認 `--since` 日期、確認信件寄件者真的是 `noreply@uber.com`（有時公司帳號是別的）|
| 同日連續行程沒推薦 | 第一趟還沒分配 → 沒 anchor | 正常 — 第一趟需要使用者選 |
| 私人行程沒被歸檔 | 沒有 — 私人會歸檔，只是 summary 不算 | 確認 `[私人]` tag 在檔名 |

---

## 不在範圍

| 別人問你 | 你回 |
|---|---|
| 修改 Uber 處理費電子發票統編 | 那要去 Uber Formosa 寄的「電子發票通知信」裡的關貿網路網站改 — 不是這個 skill 做的事 |
| 自動從 Gmail 抓 Uber 收據 | v2 才會做（OAuth + Gmail filter），目前要使用者手動下載 |
| Uber Eats 收據 | 這個 skill 不處理外送 |
| 高鐵 / 台鐵車票 | 用姊妹 skill `thsr-receipt` / `tra-receipt` |
| 把計程車車資變成可扣抵發票 | 系統限制，做不到 |

---

## 快速指令參考

```bash
# 列公司
python3 ~/.claude/skills/uber-receipt/scripts/main.py --list

# 看單一 PDF 解析結果（不動檔）
python3 .../main.py --inspect '/path/to/receipt_xxx.pdf'

# 歸檔單檔
python3 .../main.py --single '/path/to/receipt_xxx.pdf' --company-label 我的公司
python3 .../main.py --single '/path/to/receipt_xxx.pdf' --personal

# 批次掃描（給 Claude 互動用）
python3 .../main.py --batch '/path/to/folder/' --default-company 我的公司 --json

# Gmail 自動抓（需先設 App Password）
python3 .../gmail_fetcher.py --check                                  # 檢查設定
python3 .../main.py --from-gmail --default-company 我的公司 --json     # 全自動
python3 .../main.py --from-gmail --since 2026-04-01 --refetch         # 重抓特定區間

# 產月報
python3 .../main.py --report 2026-04
```
