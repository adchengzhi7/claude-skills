"""跟 tmux 有關的只有兩件事：查每個 pane 現在在哪個視窗、把畫面切到某個視窗。沒裝 tmux 也能用，只是卡片點不過去。"""
import os
import re
import shutil
import subprocess

PANE_RE = re.compile(r"%[0-9]+")  # 一律用 fullmatch 比對
# launchd／桌面捷徑啟動時 PATH 很短，常見位置自己找一遍
_CANDIDATES = ("/opt/homebrew/bin/tmux", "/usr/local/bin/tmux", "/usr/bin/tmux")


def find_tmux():
    found = shutil.which("tmux")
    if found:
        return found
    return next((p for p in _CANDIDATES if os.access(p, os.X_OK)), None)


def pane_of(tmux_field):
    """Claude Code 記的位置長這樣：'工作階段:@32.%33'，只要最後的 pane 編號（tmux 重新編號視窗時它不會變）。"""
    if not isinstance(tmux_field, str) or "." not in tmux_field:
        return ""
    pane = tmux_field.rsplit(".", 1)[-1]
    return pane if PANE_RE.fullmatch(pane) else ""


def list_panes(tmux_bin):
    """回 {pane 編號: (工作階段:視窗號, 視窗名)}。查不到（沒裝、tmux 沒開、逾時）回 None——
    None 跟「空的 {}」要分開：None＝不知道，不能當成「所有人都不在 tmux 裡」。"""
    if not tmux_bin:
        return None
    try:
        # errors="replace"：視窗名可能不是合法的 UTF-8（舊編碼取的名字），照規矩解會丟錯、整間辦公室都看不到
        r = subprocess.run([tmux_bin, "list-panes", "-a", "-F", "#{pane_id}\t#{session_name}:#{window_index}\t#{window_name}"],
                           capture_output=True, text=True, errors="replace", timeout=5)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    out = {}
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and PANE_RE.fullmatch(parts[0]):
            out[parts[0]] = (parts[1], parts[2])
    return out


def select_window(tmux_bin, pane):
    """只做 select-window 一個動作，目標只收 pane 編號。回 (成功?, 錯誤訊息)。"""
    if not tmux_bin:
        return False, "這台沒裝 tmux"
    if not isinstance(pane, str) or not PANE_RE.fullmatch(pane):
        return False, "位置格式不對"
    try:
        r = subprocess.run([tmux_bin, "select-window", "-t", pane], capture_output=True, text=True, errors="replace", timeout=5)
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        return False, str(e)
    return r.returncode == 0, (r.stderr or "").strip()
