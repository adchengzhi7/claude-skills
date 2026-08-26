# 從零架起你自己的預覽站

> 路徑說明：`{SKILL_DIR}` ＝ 本 skill 的安裝目錄（手動裝在 `~/.claude/skills/` 就是那裡，plugin 安裝則在 plugin 快取目錄）。

大概十分鐘。做完你會有一個網址，你自己的手機、平板、筆電打得開，別人打不開。

## 你需要什麼

| | |
|---|---|
| **一台常開的機器** | Mac mini、NAS、舊筆電都行。**它關機時站台就不見了**——這是這套做法唯一的硬條件 |
| **Tailscale 帳號** | 免費方案就夠。要在「常開的那台」和「你要看的裝置」上都裝 |
| **Python 3** | macOS 內建。Linux 通常也有 |

沒有常開的機器就別往下走了——這套做法幫不上忙。

---

## 步驟一：裝 Tailscale，查出你的私網 IP

在**常開的那台機器**上裝好 Tailscale 並登入，然後：

```bash
tailscale ip -4
```

會印出一個 `100.x.y.z` 開頭的位址。**記下來**，等一下要填。

這個位址只在你的 Tailscale 網路裡存在。外面的網際網路連不到它——
這就是整套做法的安全基礎。

在你的手機、平板上也裝 Tailscale 並用**同一個帳號**登入。

## 步驟二：寫設定檔

```bash
mkdir -p ~/.config/previews
cp {SKILL_DIR}/config.example.env ~/.config/previews/config.env
$EDITOR ~/.config/previews/config.env
```

最少要改一個：把 `PREVIEWS_BIND_IP` 換成步驟一查到的位址。

> **為什麼設定要獨立成一個檔**：這樣 skill 本身不含任何一台機器的資訊，
> 可以原封不動分享給別人；你的 IP 與路徑留在你自己的設定檔裡，不會跟著散出去。

**不要把 `PREVIEWS_BIND_IP` 填 `0.0.0.0`。** 那會綁到這台機器的每一個網路介面，
包含你家或辦公室的 Wi-Fi——同一個網路下的任何裝置都連得進來。腳本會擋這件事。

## 步驟三：建立站台

```bash
{SKILL_DIR}/scripts/serve.sh init
{SKILL_DIR}/scripts/serve.sh start
```

`init` 會建好資料夾與首頁，`start` 把站台跑起來。
用手機（已連上同一個 Tailscale 帳號）打開 `http://<你的IP>:8787/` 應該就看得到空清單。

打不開的話先確認：手機的 Tailscale 有沒有連上、常開那台有沒有睡著。

## 步驟四：讓它開機自動起來

```bash
{SKILL_DIR}/scripts/serve.sh install
```

macOS 上會裝一個 launchd 服務，開機自動啟動、掛掉自動重開。

> **順序問題**：開機時站台可能比 Tailscale 早起來，那時 IP 還不存在會啟動失敗。
> 設定裡開了自動重試，等 Tailscale 上線後就會成功——看到啟動失敗先別急著改東西。

**如果你本來就有一套在顧這個站**（自己寫的 launchd、systemd、tmux），
`serve.sh status` 會顯示「本 skill 沒裝過」但站台是活著的。
**這種情況不要再 install**，兩個程序搶同一個 port 會打架。

## 步驟五：發第一份頁面

```bash
echo '<h1>會動了</h1>' > /tmp/hello.html
{SKILL_DIR}/scripts/publish.sh /tmp/hello.html --title "第一份測試" --desc "確認整條路走得通"
```

印出網址、手機打得開、首頁上多一張卡片——三個都對就完成了。

---

## 常見卡關

| 症狀 | 原因 | 怎麼辦 |
|---|---|---|
| 手機打不開 | Tailscale 沒連上，或常開那台睡著了 | 手機開 Tailscale 確認已連線；把那台的自動睡眠關掉 |
| 中文變亂碼 | HTML 沒宣告編碼 | 發佈腳本會自動補，若仍亂碼檢查檔案本身的編碼 |
| 頁面打得開但首頁沒有卡片 | 稿子直接寫在站台資料夾裡了 | 寫在別處再發佈（腳本現在會擋） |
| 站台常常掛掉 | 沒裝成開機服務 | 跑 `serve.sh install` |
| 找不到存取紀錄 | 看錯檔 | 在 `.server.err`，不是 `.server.log` |

## 之後要記得的兩件事

1. **這個站沒有登入機制。** 它安全的唯一原因是只有你的 Tailscale 裝置連得到。
   要給外人看請走有登入的管道，不要對它開 Funnel（理由見 `SKILL.md`）。
2. **定期清。** 它會慢慢變成傳檔用的雜物間，清理方法見 `SKILL.md`。
