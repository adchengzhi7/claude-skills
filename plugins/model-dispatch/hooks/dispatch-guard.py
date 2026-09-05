#!/usr/bin/env python3
"""
dispatch-guard（PreToolUse / Agent）— 萬用 agent 不准「不選模型」就派工。

問題：general-purpose 這類什麼都能做的 agent 沒有模型綁定，派工時不寫 model
就一律繼承主 session 的模型。主 session 通常跑最貴的檔位，於是「讀一份檔案」
「找一段逐字稿」這種活也跑在最貴檔位，而且從外面看不出來。

做法：不做語意判斷（猜「這件事該不該便宜」一定誤判），改成結構性規則：
  **派 general-purpose / claude（或沒寫 subagent_type）時，必須明確帶 model。**
選什麼由當下判斷，但不能靠繼承預設偷偷跑在最貴檔位——把「我會記得」換成「系統不讓我不選」。

放行：
  - 有 model 欄位（不管選哪個）＝已經做過決定
  - 具名專才 agent（code-reviewer / feature-builder / …）＝frontmatter 已綁模型
  - fork＝依設計必然繼承主模型，指定 model 也會被忽略
  - Explore / Plan＝內建唯讀搜尋/規劃 agent，預設不管；要納管設環境變數
    DISPATCH_GUARD_ALSO=Explore,Plan

fail-open：解析不出輸入就放行（這層是減速帶，不是唯一防線）。
"""
import json
import os
import sys

# 只管這幾個「什麼都能做」的入口；具名專才有自己的 frontmatter 綁定
CATCH_ALL = {"general-purpose", "claude", ""}
# 依設計繼承主模型、指定也沒用
INHERIT_BY_DESIGN = {"fork"}

extra = os.environ.get("DISPATCH_GUARD_ALSO", "")
CATCH_ALL |= {s.strip() for s in extra.split(",") if s.strip()}

GUIDE = [
    "dispatch-guard：派萬用 agent 必須明確指定 model，不要靠繼承主 session。",
    "",
    "   為什麼：general-purpose 沒有模型綁定，不寫就跟著主 session 跑（通常是最貴檔位）。",
    "   實務上這類派工有相當比例只是查資料讀檔，不需要最強的模型。",
    "",
    "   照派工表選一個（見你的 CLAUDE.md「模型派工」段；沒有就用這張）：",
    "     搜 code / 讀檔盤點 / 找資料      → model: 'haiku' 或 'sonnet'（或改派 Explore）",
    "     例行 rollout / 機械改寫          → model: 'sonnet'",
    "     寫功能 / 修 bug（有測試兜底）    → 改派已綁模型的專才 agent",
    "     code review / 深度除錯           → 改派已綁模型的專才 agent",
    "     規劃 / 架構決策 / 挑錯反方       → model: 'opus'",
    "",
    "   重下一次，把 model 寫進 Agent 呼叫的參數即可。",
]


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    # Claude Code 曾把子 agent 工具從 Task 改名成 Agent；兩個名字都收，換版不會靜默失效。
    if (data.get("tool_name") or "") not in ("Agent", "Task"):
        sys.exit(0)

    tool_input = data.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        sys.exit(0)

    subagent = (tool_input.get("subagent_type") or "").strip()
    if subagent in INHERIT_BY_DESIGN:
        sys.exit(0)
    if subagent not in CATCH_ALL:
        sys.exit(0)

    model = (tool_input.get("model") or "").strip()
    if model:
        sys.exit(0)

    label = subagent or "(未指定 subagent_type)"
    print("\n".join([GUIDE[0], f"   這次派的是：{label}"] + GUIDE[1:]), file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
