---
name: agent-usage-report
description: 統計 Claude Code 子 agent 的使用狀況（哪個 agent 被派幾次、哪些專案在用、哪些 agent 30 天沒人碰）。預設近 7 天，可指定「近 30 天」「本月」。用於每週評估哪些 agent 真的在用、哪些可以砍掉。
---

# Agent 使用狀況報告

掃描本機 transcript（`~/.claude/projects/*/*.jsonl`），統計 Agent 工具觸發的 `subagent_type`，產出 Markdown 報告。

## 執行方式

```bash
python3 {SKILL_DIR}/report.py              # 近 7 天
python3 {SKILL_DIR}/report.py --days 30    # 近 30 天
python3 {SKILL_DIR}/report.py --since 2026-04-01
python3 {SKILL_DIR}/report.py --json       # 給其他工具用
```

`{SKILL_DIR}` 是本 SKILL.md 所在目錄。

## 輸出內容

1. 總計：時間範圍、總觸發次數、活躍 session 數
2. 按 agent 排行：每個 agent 幾次、最後一次何時
3. 按專案分布
4. Kill switch 候選：範圍內 0 次觸發的已定義 agent（掃 `~/.claude/agents/` 與範圍內每個專案的 `.claude/agents/`）
5. 最近 10 次觸發樣本

想單獨追蹤幾個 agent，設環境變數 `AGENT_USAGE_TRACKED=debugger,feature-builder`，報告會多一段。

## Kill switch 判斷規則

- 30 天內 0 次觸發：建議檢討是否還需要
- 7 天內 0 次但有歷史使用：可能需求變了，列觀察
- 7 天內 3 次以上：健康使用

## 注意事項

- 資料來源只有本機 transcript，不上傳任何地方
- transcript 路徑是把 cwd 的 `/` 換成 `-`，例：`~/Projects/foo` 會變成 `-Users-<你>-Projects-foo`
- transcript 被清掉就會缺漏，這是預期行為
- 本報告只算「派了幾次」，不算「派的時候有沒有帶 model」——那個指標在 `model-dispatch-review` skill 的 `dispatch-ratio.py`
