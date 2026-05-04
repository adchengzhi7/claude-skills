# tra-receipt

自動下載台鐵購票證明 PDF 用於報帳，做成 [Claude Code](https://claude.com/claude-code) Skill / Plugin。

## 它做什麼

在 Claude Code 裡丟一句**「下載 3333333 的台鐵購票證明」**，或**直接拖一張 e訂通「訂票紀錄詳情」截圖**，PDF 就自動落地：

```
~/Downloads/tra_receipts/2026-04-27-池上-南港-NXXXXXXXXXXXX1.pdf
                         └─乘車日─┘ └起站┘└訖站┘ └─────票號─────┘
```

- 用 **票號**（每張票唯一）當檔名最後一段，方便對帳，不是訂票代碼
- 自動辨識**身分證 / 居留證統一證號**並切到對的 tab（依 ID 第 2 碼判斷）
- Headless Chromium，背景跑、不彈視窗
- PDF metadata 從 PDF 內容抽（用 `pdftotext`），比解析網頁穩

## 平台限制

⚠️ **僅支援 macOS**：用了 macOS Keychain（`security` 指令）和 `open` 指令。

## 安裝（Plugin 方式，推薦）

在你的 Claude Code 裡：

```
/plugin install agoodbarn/tra-receipt
```

或從 Marketplace（規劃中）：

```
/plugin marketplace add agoodbarn/tools
/plugin install tra-receipt@agoodbarn-tools
```

## 安裝（Git Clone 方式）

```bash
git clone https://github.com/agoodbarn/tra-receipt ~/code/tra-receipt
cd ~/code/tra-receipt
./install.sh
```

`install.sh` 會：
1. 裝 `poppler`（`pdftotext`）via Homebrew
2. 裝 `playwright` Python 套件
3. 下載 Chromium（約 150MB）
4. 把 skill 放進 `~/.claude/skills/tra-receipt/`
5. 提示你在 Keychain 設身分證 / 居留證號

## 使用

設定完之後，在 Claude Code 任意 session 裡：

```
下載 3333333 的台鐵購票證明
```

或直接貼一個 7 位數（會被當成訂票代碼）：

```
3333333
```

或拖一張 e訂通「訂票紀錄詳情」截圖進去（橘色標題、有「訂票代碼 XXXXXXX」那個畫面）。

## 直接用 CLI（不透過 Claude）

```bash
python3 ~/.claude/skills/tra-receipt/scripts/download.py 3333333
```

環境變數：

| 變數 | 用途 |
|---|---|
| `TRA_ID` | 從環境變數讀 ID（覆寫 Keychain） |
| `TRA_ID_TYPE` | `PERSON_ID`（身分證）或 `PASSPORT_NO`（居留證 / 護照），不設則自動判斷 |
| `TRA_HEADED` | `1` 開可見瀏覽器（debug 用、或要手動處理驗證碼） |

## Keychain 設定

```bash
# 第一次設定
security add-generic-password -a "$USER" -s "tra-id" -w "你的身分證或居留證號"

# 更新（要先刪再新增）
security delete-generic-password -a "$USER" -s "tra-id"
security add-generic-password -a "$USER" -s "tra-id" -w "新的號碼"

# 確認存在（不會印出值）
security find-generic-password -a "$USER" -s "tra-id" >/dev/null && echo OK
```

ID 格式：

| 類型 | 格式 | 第 2 碼 | 範例 |
|---|---|---|---|
| 身分證 | 1 英文 + 9 數字 | 1（男）/ 2（女）| A123456789 |
| 居留證統一證號 | 1 英文 + 9 數字 | 8（男）/ 9（女）| A800000014 |

腳本會依第 2 碼自動切到對的 tab（身分證字號 vs 護照號碼/統一證號）。

## 隱私與安全

- 身分證 / 居留證號**只存在 macOS Keychain**，腳本透過 `security find-generic-password` 動態讀取，**不寫入任何檔案**
- 連線都走 TLS，台鐵官方網站
- PDF 落在本機 `~/Downloads/tra_receipts/`，不上傳任何雲端
- 程式碼全公開可審計（這個 repo）

## 不在範圍內

| 不支援 | 走哪裡 |
|---|---|
| 電子票證（悠遊卡 / 一卡通 / icash 2.0）乘車證明 | https://queryweb.easycard.com.tw/tra_web/ |
| 高鐵購票證明 | T-EX App |

## 已知限制

- 只支援 macOS（Keychain + `open`）
- 需要 Python 3 + Homebrew
- 要乘車日當天（含）之後才能下載證明（台鐵規定）
- 有時頁面會跳驗證碼，這時用 `TRA_HEADED=1` 跑一次手動補

## 開發

```bash
# 直接編輯 ~/.claude/skills/tra-receipt/scripts/download.py
# 或編輯這個 repo 的 skills/tra-receipt/scripts/download.py 然後 ./install.sh 重灌

# 測試
python3 skills/tra-receipt/scripts/download.py 3333333
```

## License

MIT — 拿去改、拿去用、拿去賣，沒差。
