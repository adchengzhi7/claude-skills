# model-dispatch

Claude Code plugin：讓子 agent 自動跑在對的模型檔位。主 session 永遠不切模型，「切換」發生在每一次派子 agent 的時候。

## 解決什麼問題

貴的模型當主 session 很合理，但主 Claude 派出去的子 agent **預設會繼承主 session 的模型**。
於是「讀一份工單全文」「找一段逐字稿」這種活也跑在最貴檔位，而且從外面完全看不出來。

靠「我會記得帶 model」不會成功。實測基線：160 次派工裡只有 21 次明確帶了模型（13%）。

## 怎麼解：四層結構，各做一件事

| 層 | 做什麼 | 在哪 |
|---|---|---|
| 1. 專才 agent 綁死模型 | 每個具名 agent 的 frontmatter 寫死 `model:`，派它時不能選也不會選錯 | 你的 `agents/*.md`，範本在 `templates/agent-frontmatter.md` |
| 2. 萬用 agent 被 hook 擋著 | 派 general-purpose 沒帶 model 就擋下、印派工表要主 Claude 重下。不做語意判斷，只逼你選 | `hooks/dispatch-guard.py`（本 plugin 自動掛） |
| 3. 派工表每次開場載入 | 任務形狀對應 model 與 effort | 貼進你的 CLAUDE.md，範本在 `templates/dispatch-table.md` |
| 4. 每週對帳 | 超過 7 天沒回顧就在 SessionStart 注入提醒；回顧用真實派工紀錄算指標 | `hooks/review-reminder.sh` ＋ `model-dispatch-review` skill |

裝了之後同一個指標從 13% 升到 89%，之後每週回顧多半判定「無錯配、不動設定」——那也是機制在運作的證據。

## 安裝

```
/plugin marketplace add adchengzhi7/claude-skills
/plugin install model-dispatch
```

裝完之後還有兩件事要你自己做（plugin 不會替你改設定）：

1. 把 `templates/dispatch-table.md` 的內容貼進你的 CLAUDE.md，照自己的模型與預算改。
2. 幫你常用的具名 agent 加上 `model:` frontmatter（範本 `templates/agent-frontmatter.md`）。

## 裡面有什麼

- `hooks/dispatch-guard.sh` ＋ `dispatch-guard.py`：PreToolUse hook，matcher 同時收 `Agent` 與 `Task` 兩個名字（工具曾改名，只收一個會靜默失效四天）。
- `hooks/review-reminder.sh`：SessionStart hook，日期戳放 `$CLAUDE_PLUGIN_DATA/last-review`（沒有這個變數就退到 `~/.claude/plugin-data/model-dispatch/`）。
- `skills/model-dispatch-review`：週回顧流程 ＋ `dispatch-ratio.py`（核心指標：萬用 agent 明確帶 model 的比例、各 agent 實際模型分布）＋ `mark-reviewed.sh`（重置計時）。
- `skills/agent-usage-report`：哪個 agent 被派幾次、哪些專案在用、哪些 30 天沒人碰（kill-switch 候選）。
- `templates/`：派工表與 agent frontmatter 範本。

## 可調的地方

| 環境變數 | 用途 | 預設 |
|---|---|---|
| `DISPATCH_GUARD_ALSO` | 把 `Explore,Plan` 也納入必須帶 model 的名單 | 不納入 |
| `MODEL_DISPATCH_REVIEW_DAYS` | 幾天沒回顧就提醒 | 7 |
| `AGENT_USAGE_TRACKED` | 報表裡單獨追蹤的 agent（逗號分隔） | 無 |

## 誠實邊界

- guard 是 **fail-open**：python3 不在或輸入解析失敗就放行。它是減速帶，不是唯一防線。
- guard 只逼你「選」，不驗證你「選得對不對」。選得對不對要看週回顧的打回率，那是滯後指標。
- Explore 與 Plan 這兩個內建 agent 預設不納管（它們本來就偏便宜的活），要管就設 `DISPATCH_GUARD_ALSO`。
- 報表只讀本機 transcript，不上傳任何東西；session 被清掉就算不到。

## 建議當範本改，不要照抄

派工表裡的模型名稱、貴便宜的分法、agent 名單都是從一個真實工作流長出來的。
你的預算、你的 agent 名單不一樣，請換成自己的。**真正值錢的是那幾條雷**（工具改名靜默失效、fail-open 的取捨、一次只動一個設定），不是表格本身。

## 授權

MIT — 見 LICENSE。使用前請看 DISCLAIMER.md。
