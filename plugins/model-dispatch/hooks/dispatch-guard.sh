#!/usr/bin/env bash
# PreToolUse hook 薄 wrapper — dispatch-guard（萬用 agent 不准「不選模型」就派工）。
# python3 不在 / guard 缺檔 → fail-open（這層是減速帶，不是唯一防線）。
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GUARD="$HERE/dispatch-guard.py"
command -v python3 > /dev/null 2>&1 || exit 0
[ -f "$GUARD" ] || exit 0
exec python3 "$GUARD"
