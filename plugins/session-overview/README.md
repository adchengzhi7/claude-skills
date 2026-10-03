# session-overview

Claude Code mod：打 `/overview`，旁邊開一個面板，一次看對話空間、花費、額度、正在跑的子 agent。

## 解決什麼問題

對話空間、花費、額度、子 agent 跑了多久，這四件事平常散在不同地方，要分別去查。
同時開好幾個 session 時，最常發生的是「額度快沒了才發現」和「不知道那個子 agent 是還在跑還是卡住了」。

這個 mod 把它們放進同一個面板，開著就自己更新。

## 長什麼樣

面板內容（數字是舉例）：

```
對話空間    18%      ███░░░░░░░░░░░  183k / 1M
本次花費    US$ 4.20
5 小時額度  23%      ███░░░░░░░░░░░  2 小時 15 分後重置
7 天額度    41%      ██████░░░░░░░░

助手（1 個在跑）
code-reviewer       已跑 3 分 12 秒  審查這次改動
最近結束
Explore             完成（跑了 40 秒）
```

- 額度和對話空間用到 75% 那一行變黃、90% 變紅。
- 子 agent 跑完會移到「最近結束」，只留最近三個；被中斷的顯示「已停止」，出錯的顯示「失敗」。

## 需要什麼

- Claude Code 的 Mods 功能（2026 年 10 月推出，仍是 early access，API 還會變）。這個 mod 在 **2.1.288** 上開發與測試，更舊的版本沒試過。
- Mods 有遠端開關，沒開到時 mod 不會載入。從 marketplace 裝的通常不會有任何提示；用 `--plugin-dir` 試的話，Claude Code 會印一行說明。
- 開發過程在終端機實際用過。桌面版只通過測試套件（測試驗的是 mod 交給介面的內容，不是介面實際畫出來的樣子），沒有實機看過。
- 介面文字是繁體中文。

## 安裝

```
/plugin marketplace add adchengzhi7/claude-skills
/plugin install session-overview
```

裝完開一個新的 session，打 `/overview`。

想先試不想裝：把這個資料夾抓下來，用 `claude --plugin-dir <資料夾路徑>` 啟動，只對那一次生效。

## 用法

| 你做 | 結果 |
|---|---|
| 打 `/overview`（回合進行中也可以打） | 打開面板 |
| 打 `/overview off`，或直接把面板關掉 | 關掉 |
| 跟 Claude 說「打開總覽面板」 | Claude 自己開，並回報有沒有開成功 |

面板預設不會自己跳出來。這個 session 開過之後，mod 重新載入時會自己開回來；你關掉之後就不會再自己開。

## 它碰得到什麼

Mod 跑在 Claude Code 自己的程序裡，權限可以很大，裝任何 mod 之前都該先看這一段。
這一個只做三件事：讀用量與子 agent 清單、記住這個 session 的讀數、畫面板。用到的引擎功能如下，可以自己跑 `claude plugin validate` 對照：

| 用到的 | 拿來做什麼 |
|---|---|
| `$.session.usage` | 讀對話空間、花費、額度 |
| `$.agent.list`、`agent.spawn`、`turn.complete` | 知道有哪些子 agent、何時開始、何時結束（只看，不改） |
| `$.clock.every`、`$.clock.now` | 每 5 秒醒來一次：面板關著時只確認「面板開著嗎」就結束；開著才重讀子 agent 清單、更新「已跑多久」 |
| `$.state` | 記住這個 session 的讀數（不跨 session、不寫檔） |
| `$.ui.*` | 畫面板、放不下時提醒 |
| `$.command.register` | 註冊 `/overview` |
| `session.start`、`session.measure`、`session.end`、`ui.close`（只看，原樣放行） | 知道 session 開始、每回合量到的用量、`/clear`、面板被關掉 |
| `$.tool.register` | 給 Claude 一個開關 `mcp__session-overview__panel`，只能開、關、查面板狀態 |

**沒有用到**：讀寫檔案、連網、執行外部程式、改你送出的訊息、攔截或改寫別的工具呼叫、改子 agent 用哪個模型。

## 已知限制

- 「本次花費」是 Claude Code 自己加總的數字（跟 `/cost` 同一個），不是帳單。
- 在這個 mod 載入之前就已經在跑的子 agent，只會顯示「在跑」，算不出跑了多久。
- 「已跑多久」每 5 秒更新一次，不是每秒；面板關著時不更新數字。
- 不是你親手叫出來的面板（重新載入時自己開回來那一次），Claude Code 要求視窗夠寬才放；沒放的話會跳一行提醒，打 `/overview` 可以直接開。
- `/clear` 之後，對話空間、花費和子 agent 清單會清掉，等下一回合才有新數字；額度那幾行會留著。
- 額度那幾行只有訂閱方案看得到，而且要等第一次回應之後才有讀數。

## 測試

```
claude plugin validate plugins/session-overview
claude plugin test plugins/session-overview
```

17 個測試：面板內容（終端機與桌面版）、子 agent 開始與結束且掛勾原樣放行、被中斷顯示已停止、沒記到開始時間的不亂算、快用完變紅、面板關著不輪詢、開過會開回來而被關掉就不再自己開、沒真的關掉不算被關掉、`/overview off`、Claude 自己開關、介面不放面板時照實說、`/clear` 後不留舊數字但額度留著、`/clear` 撞上更新時舊助手不復活、純計算、清單合併規則。

## 來歷

點子來自社群 mod [cctop](https://github.com/tomstagl/cctop)（作者 tomstagl）的介紹。程式是另外寫的，沒有讀過它的原始碼。

## License

MIT
