---
name: session-office
description: 開啟、設定、排錯「Session 辦公室」——把這台電腦上每個 Claude Code session 畫成一間辦公室的本機網頁（誰在等你、誰在跑、誰做完、誰出狀況，點卡片切 tmux 視窗）。當使用者說「開 Session 辦公室」「開辦公室」「看我所有的 session」「哪個 session 在等我」「辦公室打不開／沒更新」「幫辦公室設定分組」時觸發。職責邊界：要換長相、做自己的風格 → office-theme skill；這裡只管把它開起來、設定好、修好。
---

# Session 辦公室：開起來、設定、排錯

程式在這個 plugin 的根目錄：`run.py`（這份 SKILL.md 所在資料夾往上兩層）。下面用 `<根目錄>` 代表它。
只用 Python 內建功能，不需要安裝任何套件。

## 開起來

1. 先看是不是已經在跑（不要重複開）。port 預設 8765；`~/.config/session-office/config.json` 裡有寫 `port` 就用那個數字，下面的 8765 都換掉：
   ```bash
   curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8765/api/themes
   ```
   回 `200` 就直接把網址 `http://127.0.0.1:8765/` 給使用者，結束。
2. 沒在跑就啟動。它要一直開著才會更新，所以放在背景：
   兩種都把輸出留在 `~/.local/state/session-office/server.log`（啟動失敗時視窗會馬上關掉，沒有這個檔就看不到原因）：
   ```bash
   mkdir -p ~/.local/state/session-office
   ```
   - 使用者在 tmux 裡（有 `$TMUX`）：開一個獨立視窗跑，之後看得到也關得掉。
     ```bash
     tmux new-window -d -n office 'python3 "<根目錄>/run.py" 2>&1 | tee ~/.local/state/session-office/server.log'
     ```
   - 不在 tmux 裡：
     ```bash
     nohup python3 "<根目錄>/run.py" > ~/.local/state/session-office/server.log 2>&1 &
     ```
3. 等一兩秒，再打一次第 1 步的檢查，確認回 `200` 才告訴使用者網址。沒起來就讀 `server.log` 裡的錯誤訊息（見「排錯」）。

使用者只是想先看看長什麼樣：`python3 "<根目錄>/run.py" --demo --port 8766`，用的是示範資料，不讀任何真實對話。

不要替使用者做的事：不要改成綁 `0.0.0.0` 或任何對外的位址；不要幫忙架轉發讓別台連進來。頁面上有對話片段，對外開放要有登入機制，那不在這個工具的範圍。使用者堅持要從手機看時，說明這一點，讓他自己決定怎麼做。

## 設定

設定檔 `~/.config/session-office/config.json`（沒有就全部用預設值）。改完不用重開，幾秒內生效；只有 `port` 要重開。

```json
{
  "groups": [
    { "name": "客戶A", "color": "#d9480f", "match": "client-a|客戶A" }
  ],
  "mark": { "label": "重要", "match": "urgent|很急" },
  "ballPhrases": ["現在球在你這裡的是："],
  "theme": "pixel-office",
  "contextWindow": "auto"
}
```

- `groups`：分組（篩選鈕＋名牌色塊）。`match` 是不分大小寫的正規表示式，先比對資料夾路徑與名字，再比對對話內容。沒設就用資料夾名分組。
  幫使用者設分組時，先跑 `python3 "<根目錄>/run.py" --once` 看他實際有哪些資料夾，再提議分法。
- `mark`：符合的卡片多一個小圖示。
- `ballPhrases`：最後一句回報用這些字開頭，就當成「在等你決定」放進會議室。使用者沒有固定的回報開頭就不要設。
- `contextWindow`：`"auto"` 會看 `~/.claude/settings.json` 的預設模型；使用者說 context 百分比不準時，改成實際上限的數字（例 `200000`）。

寫錯的設定不會被安靜地忽略：頁面最上面會寫「設定檔有錯：…」。改完設定請打開頁面確認沒有這行。

## 排錯

先跑 `python3 "<根目錄>/run.py" --once`：它會整理一次、把結果印出來。印得出資料＝讀取沒問題，問題在伺服器或瀏覽器那邊。

| 看到什麼 | 原因 | 做法 |
|---|---|---|
| 「不支援原生 Windows」 | 在 Windows 上直接跑 | 這個工具刻意拒絕：它確認程式還活著的做法在 Windows 上會把那個程式中斷掉。請在 WSL 裡跑，不要想辦法繞過 |
| 找不到 `…/.claude/sessions` | Claude Code 太舊，或這台沒跑過 | 更新 Claude Code，開一個 session 再試 |
| 開不了 port | 已經有一間在跑，或 port 被別的程式佔了 | 用第 1 步確認；被佔就 `--port` 換一個 |
| 頁面寫「資料已經 N 分鐘沒更新」 | `run.py` 停了 | 重新啟動 |
| 卡片點不過去 | 那個 session 不在 tmux 裡，或沒裝 tmux | 這是正常狀態，不是壞掉 |
| 點了有切，但終端機畫面沒變 | 終端機接的是另一個 tmux session | 它只切那個 tmux session 裡的視窗；請使用者自己切到那個 tmux session |
| 有卡片在急診室寫「認不得的狀態」 | Claude Code 改版換了寫法 | 把那個狀態字回報給作者；判斷在 `office/collect.py` 的 `state_of` |
| context 百分比怪怪的 | 沒有 Moshi 時是估的 | 設 `contextWindow` |

## 回報給使用者時

給網址，加一句現在的狀況（幾個在等他、有沒有人在急診室）就好。不要把 `--once` 印出來的整份資料貼給他——裡面是對話片段。
