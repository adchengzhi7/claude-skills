# clear-handoff

Claude Code skill：在 `/clear`（清空 context）之前，把當前工作狀態打包成「可無縫續做的交接包」。

## 解決什麼問題

長 session 做到一半，context 快滿了想 `/clear`，但 clear 完新 context 什麼都不記得——
要重新解釋做到哪、檔案在哪、有什麼雷，往往比省下的 context 還貴。

這個 skill 讓你在 clear 前說一聲「準備 clear」「handoff」「打包進度」，Claude 會：

1. 盤點當前任務進度、立即下一步、關鍵檔案、已拍板的決策、環境雷
2. 掃還在跑的背景程序（`/clear` 不會停它們，但新 context 不知道它在跑）
3. 寫成 session note（`~/.claude/sessions/*.tmp`），檔頭放最顯眼的 ▶ RESUME POINT
4. 產出 1-2 條 resume prompt，clear 完直接貼回去就能接著做

## 用法

```
你：準備 clear，打包一下
Claude：（寫 session note）→ 給你一條可複製的 resume prompt
你：/clear
你：（貼上 resume prompt）→ 無縫接上
```

## 觸發語

「準備 clear」「我要清 context」「給我 resume prompts」「收尾交接」「存狀態等下繼續」「handoff」「打包進度等下接」

## 設計原則

- **可續做 > 完整摘要**：寧可把下一步寫死，也不要漂亮總結卻接不上
- **路徑/指令要能直接用**：不寫「那個檔」，寫實際路徑
- **secret 不落地**：note 只記「credential 去哪拿」，不記明文
