# tailscale-preview-site

自己架一個私人預覽站：把 HTML 報告、計畫、原型發佈上去，
**只有你自己 Tailscale 網路裡的裝置看得到**。

給誰用：常常要把長報告交出去給人在手機或平板上讀，
又不想丟到需要登入的第三方服務、或不想讓內容離開自己機器的人。

## 你需要

- 一台**常開的機器**（Mac mini / NAS / 舊筆電）—— 這是硬條件，它關機站台就不見
- Tailscale 帳號（免費方案足夠）
- Python 3

## 快速開始

```bash
mkdir -p ~/.config/previews
cp {SKILL_DIR}/config.example.env ~/.config/previews/config.env
# 把 PREVIEWS_BIND_IP 改成 `tailscale ip -4` 查到的位址
scripts/serve.sh init && scripts/serve.sh start && scripts/serve.sh install
```

完整步驟見 [SETUP.md](SETUP.md)，日常用法見 [SKILL.md](SKILL.md)。

## 有什麼

- `publish.sh` —— 一行指令發佈，自動維護首頁卡片
- 首頁內建搜尋（多詞 AND）、專案標籤篩選、Cmd+K 全站搜尋
- 「未分類頁面」區 —— 收容沒有卡片的檔案，避免東西丟進去就找不到
- `serve.sh` —— 起站、開機自動啟動、狀態檢查

## 安全模型（請先讀懂再用）

這個站**沒有登入機制**。它安全的唯一原因是綁在 Tailscale 私網 IP 上，
只有你網路裡的裝置連得到。

- 不要綁 `0.0.0.0`（腳本會擋）
- **不要對它開 Tailscale Funnel** —— Funnel 沒有登入，而且會把整個資料夾公開，
  不是只有你想給的那一頁。要給外人看請走有登入的管道。
- 它會慢慢變成傳檔用的雜物間，**要定期清**。清理方法與判斷標準見 SKILL.md。

## 授權

MIT，見 [LICENSE](LICENSE)。使用前請讀 [DISCLAIMER.md](DISCLAIMER.md)。
