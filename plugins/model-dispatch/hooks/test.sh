#!/usr/bin/env bash
# dispatch-guard 金絲雀測試：餵假的派工給閘門，確認「該擋的有擋、該放的有放、每次都有打卡」。
# 用法：bash hooks/test.sh   （全過 exit 0；有一條不過 exit 1）
# health.py 會在 Claude Code 版本變動時自動跑它。
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
TMPLOG="$(mktemp -t dispatch-guard-test)"
export DISPATCH_GUARD_LOG="$TMPLOG"
pass=0; fail=0

check() { # 名稱 期望exit JSON
  local name="$1" want="$2" json="$3" got
  printf '%s' "$json" | python3 "$DIR/dispatch-guard.py" >/dev/null 2>&1; got=$?
  if [ "$got" = "$want" ]; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL $name：期望 exit $want，實際 $got"; fi
}

check "萬用小幫手沒選模型→擋"        2 '{"tool_name":"Agent","tool_input":{"subagent_type":"general-purpose","prompt":"x"}}'
check "沒寫 subagent_type 沒選→擋"    2 '{"tool_name":"Agent","tool_input":{"prompt":"x"}}'
check "舊工具名 Task 沒選→擋"         2 '{"tool_name":"Task","tool_input":{"subagent_type":"general-purpose"}}'
check "萬用小幫手有選模型→放"        0 '{"tool_name":"Agent","tool_input":{"subagent_type":"general-purpose","model":"sonnet"}}'
check "專職小幫手→放"                0 '{"tool_name":"Agent","tool_input":{"subagent_type":"code-reviewer"}}'
check "fork→放"                      0 '{"tool_name":"Agent","tool_input":{"subagent_type":"fork"}}'
check "不是派工的工具→放"            0 '{"tool_name":"Bash","tool_input":{"command":"ls"}}'
check "看不懂的輸入→放（減速帶）"    0 'not json'

# 打卡：上面 6 次派工類呼叫都要留下一筆（Bash 與壞輸入不算）
lines=$(wc -l < "$TMPLOG" | tr -d ' ')
if [ "$lines" = "6" ]; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL 打卡筆數：期望 6，實際 $lines"; fi
blocks=$(grep -c '"decision": "block"' "$TMPLOG")
if [ "$blocks" = "3" ]; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL 擋下紀錄：期望 3，實際 $blocks"; fi

rm -f "$TMPLOG"
echo "dispatch-guard 金絲雀測試：通過 ${pass}、失敗 ${fail}"
[ "$fail" = 0 ]
