#!/usr/bin/env bash
# SessionStart hook：模型派工週回顧提醒。
# 上次回顧 >= REVIEW_DAYS（預設 7）天，就把提醒注入 context（機器強制，不靠模型記憶）。
# 回顧完成後跑 skills/model-dispatch-review/scripts/mark-reviewed.sh 重置計時。
DATA_DIR="${CLAUDE_PLUGIN_DATA:-$HOME/.claude/plugin-data/model-dispatch}"
STAMP="$DATA_DIR/last-review"
DAYS_LIMIT="${MODEL_DISPATCH_REVIEW_DAYS:-7}"
mkdir -p "$DATA_DIR" 2>/dev/null || exit 0
now=$(date +%s)
if [ ! -f "$STAMP" ]; then echo "$now" > "$STAMP"; exit 0; fi
last=$(head -1 "$STAMP" 2>/dev/null)
case "$last" in (''|*[!0-9]*) exit 0;; esac
days=$(( (now - last) / 86400 ))
if [ "$days" -ge "$DAYS_LIMIT" ]; then
  echo "模型派工週回顧已 ${days} 天沒跑。請主動問使用者：要不要現在跑「模型派工週回顧」（skill: model-dispatch-review）——近 7 天派工報表＋萬用 agent 明確帶 model 的比例＋對照派工表抓錯配＋不超過 3 行升降級建議（一次只動一個設定）。跑完後執行 mark-reviewed.sh 重置計時。"
fi
exit 0
