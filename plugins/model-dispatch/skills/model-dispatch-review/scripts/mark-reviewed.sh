#!/usr/bin/env bash
# 週回顧做完後跑這支，重置 SessionStart 提醒的計時。
DATA_DIR="${CLAUDE_PLUGIN_DATA:-$HOME/.claude/plugin-data/model-dispatch}"
mkdir -p "$DATA_DIR"
date +%s > "$DATA_DIR/last-review"
echo "已重置：$DATA_DIR/last-review"
