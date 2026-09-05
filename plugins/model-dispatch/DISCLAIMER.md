# 免責聲明 / Disclaimer

## 中文

本工具為個人生產力用途的 Claude Code plugin。

**使用前請理解：**

1. `dispatch-guard` hook 會在你派萬用 agent 又沒帶 model 時**擋下該次呼叫**（exit 2）並印指引，主 Claude 需要重下一次。這是刻意的摩擦，不是 bug。
2. 它是 **fail-open** 設計：python3 不在、或輸入解析失敗就直接放行。它是減速帶，不是唯一防線。
3. `review-reminder` 只在 SessionStart 注入一段文字提醒，**不會自動改你的設定**；升降級一律等人拍板。
4. 兩支報表腳本只讀本機 `~/.claude/projects/` 下的 transcript，**不上傳任何資料**。
5. **無擔保**：依 MIT 授權，本軟體「按現狀」提供，作者不對任何使用後果負責。

## English

A personal-productivity Claude Code plugin.

- `dispatch-guard` blocks (exit 2) an Agent call that targets a catch-all agent without an explicit `model`; that friction is intentional.
- It fails open: if python3 is missing or the input cannot be parsed, the call passes.
- The reminder hook only injects text at SessionStart; it never edits your settings.
- The report scripts read local transcripts only and upload nothing.
- Provided "AS IS" under the MIT License with no warranty.

## 通報

如使用本工具時遇到隱私 / 安全問題，請開 GitHub Issue 反映。
