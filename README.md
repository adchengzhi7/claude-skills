# Alex's Claude Skills

Alex Dee 的 [Claude Code](https://claude.com/claude-code) Skill / Plugin 集合 — 日常生活＋顧問業務用的自動化工具。

## 安裝（推薦：Marketplace 一次裝齊）

在你的 Claude Code 裡執行：

```
/plugin marketplace add adchengzhi7/claude-skills
```

之後想裝哪個 skill，挑一個：

```
/plugin install tra-receipt
```

之後我新加 skill，你只要重複 `/plugin install <name>` 就好，**不用再 add marketplace**。

## 目前提供的 Plugins

| Plugin | 用途 | 平台 | 狀態 |
|---|---|---|---|
| **[tra-receipt](./plugins/tra-receipt/)** | 自動下載台鐵購票證明 PDF 報帳，支援身分證 / 居留證 | macOS | ✅ v1.0.0 |
| _（更多敬請期待）_ | | | |

## 為什麼做這個

我是 Alex，AI 顧問業務轉型中（[agoodbarn.com](https://agoodbarn.com)）。日常工作累積的小工具不應該只放在我自己電腦裡 — 任何「報帳、整檔、跨系統搬資料」這種重複動作，都應該變成一個 skill 給整個團隊用。

這個 marketplace 是我把這些 skill 公開出來的地方。

## 設計原則

1. **本地優先**：腳本跑在你自己 Mac 上，不上傳資料、不過任何雲端
2. **隱私第一**：身分證、密碼這種放 macOS Keychain，腳本只「動態讀取」
3. **可審計**：所有程式碼公開（這個 repo）
4. **最小依賴**：用系統內建工具能搞定的就不裝套件
5. **中文友善**：UI、錯誤訊息、文件全繁體中文

## 開發 / 貢獻

每個 plugin 是 `plugins/<name>/` 底下的獨立資料夾。新增 skill 流程：

```bash
git clone https://github.com/adchengzhi7/claude-skills
cd claude-skills

# 開新 plugin 目錄
mkdir -p plugins/<new-name>/.claude-plugin plugins/<new-name>/skills/<new-name>/scripts
# 寫 plugin.json、SKILL.md、scripts/...

# 在 .claude-plugin/marketplace.json 註冊新 plugin

# 提交 PR
```

## License

[MIT](./LICENSE) — 拿去改、拿去用、拿去賣，沒差。

## 聯絡

Alex Dee · [alex@agoodbarn.com](mailto:alex@agoodbarn.com) · [agoodbarn.com](https://agoodbarn.com)
