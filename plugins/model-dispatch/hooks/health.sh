#!/usr/bin/env bash
# SessionStart hook 薄 wrapper — dispatch-guard 健康檢查（看門狗＋金絲雀測試）。
# python3 不在 / health 缺檔 → 安靜退出（健康檢查本身不能變成新的開場雜訊來源）。
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HEALTH="$HERE/health.py"
command -v python3 > /dev/null 2>&1 || exit 0
[ -f "$HEALTH" ] || exit 0
exec python3 "$HEALTH"
