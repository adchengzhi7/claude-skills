# share-skill

Claude Code skill：~/.claude/ 內任何 skill 公開分享前的 PII 審查工具。

## 用法

```bash
# 全 skill 審查
python3 ~/.claude/skills/share-skill/scripts/audit.py ~/.claude/skills/<your-skill>/

# 給 pre-commit hook 用（只審 staged files）
python3 ~/.claude/skills/share-skill/scripts/audit.py --staged-only
```

## Pre-commit hook

`~/.claude/hooks/pre-commit` 是參考實作。安裝：

```bash
cp ~/.claude/hooks/pre-commit ~/.claude/.git/hooks/pre-commit
chmod +x ~/.claude/.git/hooks/pre-commit
```

之後每次 `git commit` 自動掃 staged files。BLOCK 級 PII 會擋下 commit。

## 偵測規則

🔴 **BLOCK**（必修）：
- email（非 example.com）
- 統編（8 碼數字）
- 台灣車牌（ABC-1234 / 1234-ABC）
- 駕駛執業登記證號（NA######）
- UUID v4
- 發票號（Stripe XXX-NNNN）
- 信用卡尾 4 碼
- 寫死的密碼 / API key

🟡 **WARN**（建議改）：
- 絕對路徑 `/Users/<name>/`
- 必要文件缺失（LICENSE / DISCLAIMER / README / SKILL.md）

## 容許清單

`allowlist.json` 內列出 intentional 揭露字串（命中時降為 INFO）。

## 授權

[MIT](LICENSE) — 詳 [DISCLAIMER](DISCLAIMER.md)
