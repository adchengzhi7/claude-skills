---
name: share-skill
description: 在公開 / 分享 ~/.claude/ 內任何 skill 之前，自動審查 PII 洩漏、必要文件齊全、.gitignore 規則完整。當使用者說「準備分享 X skill」、「share-ready 審查」、「skill 可以公開了嗎」、「公開前掃一下」時觸發。掃 email / 統編 / 車牌 / Trip UUID / 發票號 / 信用卡尾碼 / 絕對路徑 / 真實人名等 PII pattern。報告問題 + 建議修法 + 阻擋有問題的 commit。
---

# share-skill — Claude 操作手冊

公開 / 分享 skill 給朋友前的審查工具。當使用者要 commit + push 任何 skill 到公開 repo 時跑這個。

## 何時觸發

- 「準備分享 uber-receipt」
- 「share-ready 審查 cloud-receipts」  
- 「這個 skill 可以公開嗎」
- 「公開前掃一下」
- Claude **應主動建議**：使用者要 commit 新 skill 時，自動跑這個再 push

## 工作流程

```bash
python3 ~/.claude/skills/share-skill/scripts/audit.py <skill-path>

# 例
python3 ~/.claude/skills/share-skill/scripts/audit.py ~/.claude/skills/cloud-receipts/
```

執行的檢查（依嚴重度）：

| 檢查項 | 嚴重度 | 失敗的話 |
|---|---|---|
| **email 洩漏** | 🔴 BLOCK | 必修才能 share |
| **統編 8 碼** | 🔴 BLOCK | 必修 |
| **車牌 / 駕駛證號 / Trip UUID** | 🔴 BLOCK | 必修 |
| **發票號 / 信用卡尾碼** | 🔴 BLOCK | 必修 |
| **真實絕對路徑** `/Users/<name>` | 🟡 WARN | 改 `~` 或 `$HOME` |
| **真實人名 / 公司名** | 🟡 WARN | 看是否 intentional（容許清單）|
| LICENSE 缺失 | 🟡 WARN | 補 LICENSE |
| DISCLAIMER 缺失 | 🟡 WARN | 補 DISCLAIMER |
| README 缺失 | 🟡 WARN | 補 README |
| `.gitignore` 沒擋常見 secret | 🟡 WARN | 補 gitignore 規則 |

→ 任何 🔴 → exit 1，使用者必修才能繼續
→ 全綠 / 只有 🟡 → 報告完成，可 commit + push

## 容許清單（intentional disclosures）

在 `~/.claude/skills/share-skill/allowlist.json` 內維護：

```json
{
  "公司名": ["豆樂逗樂"],
  "說明": "quotation-builder skill 為豆樂逗樂量身打造，description 故意提及"
}
```

scan 命中 allowlist 內字串時降為 INFO，不 BLOCK 也不 WARN。

## 修法建議（對每種 PII）

| PII 類型 | 替換建議 |
|---|---|
| email | `your@email.com` / `you@example.com` |
| 統編 | `12345678` |
| 車牌 | `ABC1234` |
| 駕駛證號 | `NA000001` |
| Trip UUID | `00000000-0000-0000-0000-000000000000` |
| 發票號（ZE / NNTAOM）| `XXXXXX-NNNNN` |
| 真實路徑 | `~/...` |

## 不在範圍

- 不掃 `~/Downloads/`、`~/.config/`（這些不在 repo 內）
- 不掃 `.git/`、`__pycache__/`
- 不掃 `node_modules/`
- 二進位檔（PDF / image）只檢查檔名是否含 PII，不解內容

## 跟 pre-commit hook 的關係

`~/.claude/.git/hooks/pre-commit` 會跑 `audit.py --staged-only`，在 commit 時當守門員。share-skill 是**手動全 skill 審查**，pre-commit 是**自動 staged 審查**，兩者互補。
