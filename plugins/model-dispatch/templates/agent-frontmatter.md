# 專才 agent 綁模型：frontmatter 範本

放在 `~/.claude/agents/<name>.md`（全域）或專案的 `.claude/agents/<name>.md`。
`model:` 寫死之後，派這個 agent 時不能選、也不會選錯。

```markdown
---
name: code-reviewer
description: 程式碼審查。改動大、碰權限／金錢／不可逆的 diff 用這個。
model: opus
tools: Read, Grep, Glob, Bash
---

（agent 的指示內容）
```

```markdown
---
name: feature-builder
description: 從需求到完整功能交付，有測試與 review 接著，所以跑便宜檔位。
model: sonnet
tools: Read, Write, Edit, Grep, Glob, Bash
---
```

## 一個實際用過的分法

| agent | model | 為什麼 |
|---|---|---|
| code-reviewer | opus | 審錯的代價高 |
| red-team（挑錯反方） | opus | 要找自己找不到的洞 |
| db-architect | opus | schema 改壞很難回頭 |
| feature-builder | sonnet | 有測試和 review 接著 |
| debugger（只調查不改碼） | sonnet | 產出是報告，人再決定 |

「快審」例外：一行熱修、機械改寫、文案調整，可以不派 code-reviewer，
改派 general-purpose 並明確帶 `model: sonnet`（實測品質夠用、零打回）。
