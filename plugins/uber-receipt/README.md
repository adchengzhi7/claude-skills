# uber-receipt

> 本文指令路徑以手動安裝於 `~/.claude/skills/` 為例；若用 plugin marketplace 安裝，路徑換成該 plugin 的安裝目錄（Claude 載入 skill 時會知道）。


> Claude Code skill：把 Uber 行程**全自動**抓下來、整理成可報帳 PDF。

從 Gmail 抓 Uber 行程信 → 用你登入 session 下載官方行程明細 PDF + 統一發票 → 從 XML 自動歸戶到對的公司 → 按月/日整理。**5 分鐘 setup，之後跟 Claude 說「整理 Uber 收據」就自動跑完**。

## ⚠️ 使用前請看 [DISCLAIMER.md](DISCLAIMER.md)

簡單說：自負風險、Uber ToS 有灰色地帶、別排程跑、報帳合規性自己跟會計確認。

---

## 30 秒看它做什麼

1. 你下個月想報帳 8 趟 Uber
2. 跟 Claude 說「整理 Uber 收據」
3. 自動完成：
   ```
   ~/Downloads/uber_receipts/2026-XX/
   └── 2026-XX-DD/
       ├── HHMM-起站-訖站-NTD<金額>-[我的公司]-行程明細.pdf
       ├── HHMM-起站-訖站-NTD<金額>-[我的公司]-發票-ZE<發票號>.pdf
       ├── ...
   ```
4. 把資料夾給財務 → 結束

---

## 安裝（macOS，5 分鐘）

### 前置
- macOS（Linux/Windows 暫不支援）
- Python 3.10+
- Google Chrome 已安裝
- 個人 Gmail 帳號（已開 2FA）— 公司 Workspace 帳號 admin 可能擋

### 步驟

```bash
# 1. 把 skill 拷貝到 Claude 的 skills 目錄
cp -r uber-receipt ~/.claude/skills/

# 2. 跑 wizard（5 步走完所有 setup）
python3 ~/.claude/skills/uber-receipt/scripts/main.py --wizard
```

Wizard 會引導你：
1. 安裝 Python 套件 (pdfplumber + playwright + chromium)
2. 建 Gmail App Password 並存進 macOS Keychain
3. 開瀏覽器登入 Uber（一次就好，自動偵測完成）
4. 設定一家公司（只要統編，自動反查全名）
5. 試跑 dry-run 確認連線 OK

---

## 怎麼用

設定完之後：

**全自動（推薦）**
跟 Claude Code 說：
- 「整理 Uber 收據」
- 「處理本月 Uber」
- 「Uber 報帳」

**手動跑指令**
```bash
# 全自動：抓 Gmail + 下載官方 PDF + 自動歸戶 + 歸檔
python3 ~/.claude/skills/uber-receipt/scripts/main.py --from-gmail

# 只抓特定區間
python3 .../main.py --from-gmail --since 2026-04-01

# 重抓（略過 processed log）
python3 .../main.py --from-gmail --refetch
```

---

## 常見問題

### Q: 為什麼需要登入 Uber 兩次（Gmail + Uber）？
- **Gmail**：抓信件知道你搭過哪些 Uber
- **Uber**：用你登入 session 才能下載官方 PDF + 統一發票

兩個都是一次性 setup，session 永久保留，之後零互動。

### Q: 公司 Google Workspace 帳號 admin 禁用 App Password 怎麼辦？
目前無解（Wizard 會在 Step 2 偵測到並告知）。可以：
- 用個人 Gmail
- 或手動下載 PDF 放到 `~/Downloads/`，跟 Claude 說「整理本批 Uber」

### Q: 為什麼歸戶到的公司是 XX 不是 YY？
Uber Formosa 開立電子發票時依**你 Uber app 內當下設的統編**。要改 → Uber app → 設定 → 收據資訊 → 改統編。新行程才會用新統編。**已開立的發票永久鎖定，無法改買方**。

### Q: 計程車車資（$472 那段）會有統一發票嗎？
**不會**。台灣多元計程車制度上不開統一發票（系統限制），只有 Uber 處理費（$10）那段由 Uber Formosa 開電子發票。所以本工具產生的 PDF 包含：
- 行程明細 PDF（含完整金額、起訖、車牌、車隊、駕駛證號）— 可作為**費用憑證**
- 統一發票 PDF（僅 $10 處理費部分）— 可作為**扣抵 5% 營業稅憑證**

是否能核銷請跟貴公司財務確認，不同公司政策差異大。

### Q: 「私人」行程怎麼處理？
Wizard 不處理。日後跑 `--from-gmail` 時 Claude 會列建議表給你逐筆確認，可以標記私人 → 歸檔但不算進報表。

### Q: 安全？
- App Password 存 macOS Keychain（非明文檔）
- IMAP over TLS (port 993)
- 不傳任何資料到第三方 server，全本地
- 程式碼在 `~/.claude/skills/uber-receipt/scripts/`，可以自己審

---

## 檔案路徑

| 用途 | 路徑 |
|---|---|
| Skill 程式 | `~/.claude/skills/uber-receipt/` |
| 設定（公司清單） | `~/.config/receipts/companies.json` |
| 設定（Gmail email） | `~/.config/receipts/gmail.json` |
| Gmail App Password | macOS Keychain (`uber-receipt-gmail`) |
| Uber 登入 session | `~/.config/receipts/uber-chrome-profile/` |
| 已處理紀錄 | `~/.config/receipts/uber-processed.json` |
| **歸檔 PDF（你要的）** | `~/Downloads/uber_receipts/YYYY-MM/YYYY-MM-DD/` |

---

## 移除

```bash
# 1. 刪 skill
rm -rf ~/.claude/skills/uber-receipt

# 2. 刪設定 + session
rm -rf ~/.config/receipts

# 3. 刪 Keychain（看 EMAIL 替換）
security delete-generic-password -a 'YOUR@gmail.com' -s 'uber-receipt-gmail'

# 4. 撤銷 Gmail App Password
# https://myaccount.google.com/apppasswords → 找 uber-receipt → 撤銷
```

---

## 授權

[MIT](LICENSE)

僅限個人用途整理自己的 Uber 行程紀錄。詳見 [DISCLAIMER](DISCLAIMER.md)。
