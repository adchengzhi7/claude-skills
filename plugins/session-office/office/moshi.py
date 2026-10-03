"""選配：有裝 Moshi（手機／平板遙控 Claude Code 的 App）就借它的資料補一個數字。

辦公室本身不需要 Moshi。Claude Code 的對話紀錄裡算得出「用了多少 token」，但看不出這個 session 的上限是 20 萬還是 100 萬，
所以沒有 Moshi 時「context 還剩幾 %」是估的；Moshi 的 hook 直接收到 Claude Code 給的百分比，有它就用它的。
只讀 Moshi 的資料夾，不改它。
"""
import json
import os

DEFAULT_DIR = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "Moshi", "claude-sessions")


def available(moshi_dir):
    return bool(moshi_dir) and os.path.isdir(moshi_dir)


def context_remaining(moshi_dir, session_id):
    """回 0～100 的整數；沒裝、沒這個 session、欄位怪掉都回 None（不亂猜）。"""
    if not available(moshi_dir):
        return None
    try:
        with open(os.path.join(moshi_dir, session_id + ".json"), encoding="utf-8") as fh:
            v = json.load(fh).get("contextRemaining")
    except (OSError, ValueError, AttributeError):
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 100:
        return None
    return int(v)
