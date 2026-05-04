---
name: tra-receipt
description: 自動下載台鐵購票證明 PDF 用於報帳。當使用者說「下載台鐵購票證明」、「台鐵報帳」、「幫我抓台鐵車票」、提供 7-8 位數的台鐵訂票代碼、或貼出台鐵 e訂通「訂票紀錄詳情」截圖時觸發。也適用於使用者只丟訂票代碼數字（如「3333333」）但上下文是出差/報帳的情境。
---

# 台鐵購票證明自動下載

從台鐵官網下載報帳用的購票證明 PDF，自動命名並歸檔到 `~/Downloads/tra_receipts/`。

## 觸發判斷

- 使用者直接給訂票代碼（7-8 位數字）
- 使用者貼出台鐵 e訂通「訂票紀錄詳情」截圖（橘色標題、有「訂票代碼」「乘車日期」「車種車次」欄位）
- 使用者說「下載台鐵購票證明」、「報帳要的台鐵車票」、「台鐵 receipt」

## 執行步驟

### 1. 取得訂票代碼

- 截圖 → 從橘色「訂票代碼 XXXXXXX」按鈕讀出數字
- 直接給數字 → 直接用

### 2. 執行下載腳本

```bash
python3 ~/.claude/skills/tra-receipt/scripts/download.py <訂票代碼>
```

腳本會：
1. 從 macOS Keychain 讀身分證字號（service: `tra-id`）
2. Playwright headless 連到 https://tip.railway.gov.tw/tra-tip-web/tip/tip001/tip121/query
3. 自動填表、查詢、下載 PDF
4. 命名為 `{乘車日期}-{起站}-{訖站}-{訂票代碼}.pdf` 存到 `~/Downloads/tra_receipts/`

### 3. 回報結果

腳本成功會印出儲存路徑。確認檔案存在後告訴使用者，並用 `open` 把資料夾開起來方便他繼續報帳：

```bash
open ~/Downloads/tra_receipts/
```

## 首次設定（只做一次）

```bash
pip3 install --break-system-packages playwright
python3 -m playwright install chromium
security add-generic-password -a "$USER" -s "tra-id" -w "你的身分證字號"
```

## 常見錯誤處理

- **Keychain 找不到 tra-id**：腳本會明確提示要跑哪一行命令
- **Headless 模式失敗（可能跳驗證碼）**：腳本會自動 fallback 到 headed 模式，使用者可在浮出的瀏覽器手動補驗證碼，腳本繼續完成下載
- **訂票代碼還沒到乘車日**：台鐵規定要乘車日當天/之後才能下載，腳本會回報「查無資料」

## 不在範圍內

- 電子票證（悠遊卡、一卡通、icash 2.0）的乘車證明 → 走另一個系統 https://queryweb.easycard.com.tw/tra_web/，不在這個 skill 內
- 高鐵購票證明 → 不適用，高鐵走 T-EX App
