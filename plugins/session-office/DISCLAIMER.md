# 免責聲明 / Disclaimer

## 中文

本工具為個人生產力用途的 Claude Code plugin。

**使用前請理解：**

1. 它會讀本機的 `~/.claude/sessions/`、`~/.claude/projects/`（對話紀錄）與 tmux 的視窗清單；有裝 Moshi 時多讀它的 session 資料夾。**全部唯讀、不上傳任何資料。**
2. 頁面上會出現你的**對話片段**（最後一句話、它在等你什麼）。伺服器只綁 `127.0.0.1`，但同一台電腦上能開瀏覽器的人都看得到；螢幕分享或截圖前請留意，示範請用 `--demo`。
3. **別人給的外觀包是程式**（`theme.js` 會在頁面裡執行）。頁面有限制只能載入本機的東西，但擋不住存心的外觀包。安裝前請先讀過。
4. 點卡片會執行 `tmux select-window` 切換你的 tmux 視窗，除此之外不對 tmux 或 Claude Code 做任何寫入。
5. 它讀的是 Claude Code 目前版本寫出來的檔案格式，**不是官方公開的介面**；Claude Code 改版後可能要跟著更新。認不得的狀態會標出來，不會當成正常。
6. 「context 還剩幾 %」在沒有 Moshi 時是估計值。
7. **不支援原生 Windows**（程式會拒絕啟動）。多人共用的主機不要開：同一台電腦上的其他帳號連得到它。
8. **無擔保**：依 MIT 授權，本軟體「按現狀」提供，作者不對任何使用後果負責。

## English

A personal-productivity Claude Code plugin.

- Reads local Claude Code session state, transcripts and the tmux window list (plus Moshi's session folder if installed). Read-only; uploads nothing.
- The page shows snippets of your conversations. The server binds to 127.0.0.1 only; use `--demo` for screenshots or demos.
- A theme is code (`theme.js` runs in the page). A content-security policy limits it to local resources but cannot stop a deliberately malicious theme. Read a theme before installing it.
- Clicking a card runs `tmux select-window`; nothing else is written to tmux or Claude Code.
- It relies on file formats written by the current Claude Code version, which are not a public interface and may change.
- Native Windows is not supported (it refuses to start). Do not run it on a shared multi-user host.
- Provided "AS IS" under the MIT License with no warranty.

## 通報

如使用本工具時遇到隱私 / 安全問題，請開 GitHub Issue 反映。
