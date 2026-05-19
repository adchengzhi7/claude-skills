# Alex's Claude Skills

[Claude Code](https://claude.com/claude-code) 的 skill / plugin 集合。**你不直接用、是給 Claude 用**。

> 這個 marketplace 設計給「**有 Claude Code、想交給 Claude 處理日常瑣事**」的人。Skill 一次安裝，之後 Claude 自己看 skill 內附的操作手冊執行。

---

## 用 vs 不用 的差別

**沒裝這個 skill：**

> 你：「幫我下載 04/08 那張高鐵票的證明」  
> Claude：「我不知道怎麼下載。你可以到 ptis.thsrc.com.tw 手動操作⋯⋯」

**裝了之後：**

> 你：「幫我下載 04/08 那張高鐵票的證明」  
> Claude：[自動觸發 thsr-receipt → 列你的公司清單問選哪家 → 跑下載 → PDF 落到 `~/Downloads/thsr_receipts/2026-04/...`]

每個 skill 都有專屬的 SKILL.md 操作手冊，**Claude 拿到就會知道整套流程**（包含環境檢查、輸入解析、錯誤排除）。

---

## 一次安裝、永久受用

在你的 Claude Code 裡：

```
/plugin marketplace add adchengzhi7/claude-skills
/plugin install tra-receipt
/plugin install thsr-receipt
/plugin install uber-receipt
/plugin install cloud-receipts
/plugin install google-bills
/plugin install share-skill
/plugin install meeting-notes
```

> 第一行告訴你的 Claude 哪裡找 plugin，其餘各裝一個 plugin。只裝需要的就好。

之後我有新的 skill，你只要 `/plugin install <new-name>` 就好，**不用再 add marketplace**。

---

## 第一次跟你的 Claude 講

裝完後，把這段直接丟給 Claude（或讓它自己摸 — SKILL.md 寫好了）：

> 「幫我設定一下 tra-receipt 跟 thsr-receipt。看缺什麼依賴就告訴我裝、需要我提供什麼資料就問我。」

Claude 會：

1. 檢查 `qpdf` / `playwright` / `chromium` / `pdftotext` 有沒裝；缺什麼**告訴你跑哪行 brew/pip 指令**
2. 問你身分證 / 居留證號（台鐵需要）→ 引導你寫進 macOS Keychain
3. 問你最常請款的公司（label + 統編 + 全名）→ 寫進 `~/.config/thsr-receipt/companies.json`
4. 全部好了之後，可以試跑一張票（你給訂票代碼 / 截圖即可）

---

## 日常用法（自然語言）

裝完後你不用記 CLI、不用記參數。直接跟 Claude 講：

```
下載 3333333 的台鐵購票證明
```

```
下載高鐵 04/29 那張，請款給台積電
```

```
[拖一張 e訂通截圖]
```

```
[拖一張 T Express 票證資訊截圖] 我要報給鴻海
```

```
[拖一張紙本車票照片]
```

每次 Claude 都會主動列你的公司清單問「這次給哪家」，**不會自作主張用上次那家**（避免報錯帳）。

---

## 目前的 plugins

| Plugin | 用途 | 平台 |
|---|---|---|
| **[tra-receipt](./plugins/tra-receipt/)** v1.1 | 自動下載台鐵購票證明 PDF（支援身分證 / 居留證統一證號）| macOS |
| **[thsr-receipt](./plugins/thsr-receipt/)** v1.2 | 自動下載台灣高鐵購票證明 / 交易紀錄 PDF（T Express + 磁票/紙票，含統編戳章）| macOS |
| **[uber-receipt](./plugins/uber-receipt/)** v1.0 | 整理 Uber 行程 PDF + 統一發票（Gmail 自動抓、官方 PDF 下載、XML 反查歸戶）| macOS |
| **[cloud-receipts](./plugins/cloud-receipts/)** v1.0 | 從 Gmail 自動抓 SaaS 訂閱發票（Vercel / Supabase / Anthropic / Netlify 等）| macOS |
| **[google-bills](./plugins/google-bills/)** v1.0 | 從 Gmail 抓 Google Payments 帳單 PDF（Workspace + GCP），自動分流月份資料夾 | macOS |
| **[share-skill](./plugins/share-skill/)** v1.0 | 公開 skill 前自動掃 PII 洩漏（email / 統編 / 車牌 / 發票號等），含 pre-commit hook | macOS |
| **[meeting-notes](./plugins/meeting-notes/)** v1.0 | 把語音自動轉的會議逐字稿整理成結構化會議記錄（摘要 / 決議 / 待辦 / 待釐清）| 跨平台 |
| _（更多會陸續上架）_ | | |

收據類 plugin 都做月份分檔（`~/Downloads/.../2026-04/...`）方便月報帳整批拉；meeting-notes 是純 prompt 能力、免裝相依套件。

---

## 設計原則

1. **本地優先**：腳本跑在你 Mac 上、不上傳資料、不過任何雲端
2. **隱私第一**：身分證、密碼、統編這種**不寫入 git track 的檔**（用 macOS Keychain + `~/.config/`，gitignore 雙重保險）
3. **可審計**：所有程式碼公開（這個 repo），任何 Claude 看得到完整邏輯
4. **最小依賴**：能用 macOS 內建工具就不裝套件
5. **中文友善**：UI、錯誤、文件全繁體中文

---

## 給工程師朋友的注意事項

如果你不是用 `/plugin install` 而是直接 git clone：

```bash
git clone https://github.com/adchengzhi7/claude-skills ~/code/claude-skills
ln -s ~/code/claude-skills/plugins/tra-receipt/skills/tra-receipt ~/.claude/skills/tra-receipt
ln -s ~/code/claude-skills/plugins/thsr-receipt/skills/thsr-receipt ~/.claude/skills/thsr-receipt
```

或者跑各 plugin 的 `install.sh`（如果有的話）。

依賴：
```bash
brew install qpdf poppler
pip3 install --break-system-packages playwright
python3 -m playwright install chromium
```

---

## 開新 skill 想貢獻？

每個 skill 是 `plugins/<name>/` 底下的獨立資料夾。標準結構：

```
plugins/<name>/
├── .claude-plugin/plugin.json   # plugin 識別
├── skills/<name>/
│   ├── SKILL.md                 # ★ Claude 看的操作手冊（含環境檢查、錯誤 cookbook）
│   └── scripts/                 # 真正執行的程式碼
└── README.md                    # 給人類看的高階說明
```

**SKILL.md 要寫成「Claude 操作手冊」**，包含：

1. **觸發判斷**：什麼訊號看到要啟動
2. **環境自檢**：依賴 / 設定檔在不在
3. **輸入解析**：圖片太大要轉、URL 要 parse、邊界情境
4. **執行步驟**：每步具體 bash / python 指令
5. **錯誤 cookbook**：每種錯誤訊息對應原因 + 修法
6. **不在範圍**：明確告訴 Claude 不要做什麼

**寫得越好、對方 Claude 越自主**。

---

## License

[MIT](./LICENSE) — 拿去改、拿去用、拿去賣，沒差。

---

## 聯絡

Alex Dee · [alex@agoodbarn.com](mailto:alex@agoodbarn.com) · [agoodbarn.com](https://agoodbarn.com)
