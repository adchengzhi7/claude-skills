---
name: tra-receipt
description: 自動下載台鐵購票證明 PDF 用於報帳。當使用者說「下載台鐵購票證明」、「台鐵報帳」、「幫我抓台鐵車票」、提供 7-8 位數的台鐵訂票代碼、或貼出台鐵 e訂通「訂票紀錄詳情」截圖時觸發。也適用於使用者只丟訂票代碼數字（如「3333333」）但上下文是出差/報帳的情境。
---

# 台鐵購票證明自動下載 — Claude 操作手冊

從台鐵官網下載報帳用的 PDF，自動歸檔到 `~/Downloads/tra_receipts/YYYY-MM/`。
**這份檔案是寫給「執行這個 skill 的 Claude」看的，不是寫給最終使用者**。

---

## 觸發判斷

明確訊號：
- 使用者貼出台鐵 e訂通「訂票紀錄詳情」截圖（橘色標題列、有「已取票」「已退換票」狀態徽章、橘色「訂票代碼 XXXXXXX」按鈕）
- 使用者說「下載台鐵購票證明」、「台鐵報帳」、「報帳要的台鐵車票」

模糊訊號（看上下文判斷）：
- 使用者只丟一串 7-8 位數字（例：`3333333`），且對話脈絡是出差 / 報帳
- 使用者貼一張看起來像火車票的照片或截圖

---

## Phase 0：環境自我檢查（首次或感覺有問題時）

```bash
# 必備工具
which python3 || echo "❌ 缺 python3 → brew install python"
which pdftotext || echo "❌ 缺 pdftotext → brew install poppler"

# Python 套件
python3 -c "import playwright" 2>&1 | grep -q ModuleNotFoundError && echo "❌ 缺 playwright → pip3 install --break-system-packages playwright && python3 -m playwright install chromium"

# Keychain 是否有 tra-id
security find-generic-password -a "$USER" -s "tra-id" -w >/dev/null 2>&1 || echo "❌ 缺身分證/居留證 → 引導使用者執行：security add-generic-password -a \"\$USER\" -s \"tra-id\" -w \"<身分證或居留證號>\""
```

如果有任一缺項：**先告訴使用者具體缺什麼、要跑什麼指令裝**，不要直接動手裝（特別是 Keychain，要使用者自己貼身分證號）。

---

## Phase 1：取得訂票代碼

### 從文字
直接 7-8 位數字 → 用。

### 從截圖
e訂通「訂票紀錄詳情」畫面 → 找橘色按鈕「**訂票代碼 XXXXXXX**」讀數字。

### 從照片（紙本車票，少見）
找票面上的訂票代碼欄位（通常右側）。

### 大圖檔讀不了
若截圖是 HEIC 或 > 256KB 讀不進來，先轉檔：

```bash
sips -s format jpeg -s formatOptions 70 --resampleWidth 800 \
  "/Users/alexd/Downloads/IMG_XXXX.HEIC" --out "/tmp/IMG_XXXX.jpg"
```

再 Read JPG。

---

## Phase 2：執行下載

```bash
python3 ~/.claude/skills/tra-receipt/scripts/download.py 3333333
```

腳本會：
1. 從 Keychain 讀身分證號（auto-detect 台灣身分證 vs 居留證統一證號 → 切到對的 radio）
2. Playwright headless 上 `www.railway.gov.tw/tra-tip-web/tip/tip001/tip115/query`
3. 填表、查詢、下載 PDF
4. 從 PDF 內容抽出乘車日 / 起站 / 訖站 / 票號（用 `pdftotext`）
5. 存到 `~/Downloads/tra_receipts/YYYY-MM/{乘車日}-{起站}-{訖站}-{票號}.pdf`

---

## Phase 3：回報

```bash
open -R ~/Downloads/tra_receipts/YYYY-MM/<file>.pdf
```

告訴使用者：
- 檔案路徑
- 票號（從 PDF 抽到的，每張票唯一）
- 乘車資訊（日期、起訖站）

---

## 錯誤 cookbook

| 錯誤訊息 | 原因 | 修法 |
|---|---|---|
| `Keychain 沒找到 tra-id` | 還沒設身分證 | 引導使用者跑 `security add-generic-password ...`（**不要替使用者打**身分證號）|
| `身分證字號錯誤`（HSR 紅字）| 第 2 碼不是 1/2 | auto-detect 已會切到「護照號碼/統一證號」radio；若仍失敗：請使用者驗證 keychain 內容是否打錯 |
| `查無資料` / `找不到下載按鈕` | 訂票代碼錯，或還沒到乘車日 | 確認訂票代碼、確認乘車日已過或當天 |
| `Headless 模式失敗（驗證碼）` | 偶發 captcha | 腳本會自動 fallback 到 headed mode，瀏覽器會浮出讓使用者手動補 |

---

## 居留證使用者

新版統一證號格式：1 英文 + 9 數字（第 2 碼是 8 或 9）。
腳本會 auto-detect、切到「護照號碼/統一證號」radio，使用者**不用做任何事**。

---

## 不在範圍

| 別人問你做什麼 | 你回什麼 |
|---|---|
| 電子票證（悠遊卡 / 一卡通 / icash 2.0）乘車證明 | 走 https://queryweb.easycard.com.tw/tra_web/，不是這個 skill |
| 高鐵購票證明 | 用姊妹 skill `thsr-receipt` |
| 退票證明 | 已退票無購票證明可下載；要退票證明走台鐵客服 |
| 不知道訂票代碼 | 引導使用者開 e訂通 App → 訂票紀錄查詢，告訴他在哪裡看 |
