---
name: model-dispatch-review
description: 每週一次的「模型派工對帳」——用實際派工紀錄算萬用 agent 明確帶 model 的比例、對照派工表抓錯配、給不超過 3 行升降級建議、決策留檔。當使用者說「模型派工回顧」「派工對帳」「看子 agent 有沒有跑對模型」「這週 agent 用得怎樣」，或 SessionStart 提醒說回顧到期時觸發。
---

# 模型派工週回顧

目的只有一個：**抓「有沒有照派工表做」，不是重新設計派工表。**
派工表本身在使用者的 CLAUDE.md（範本見本 plugin 的 `templates/dispatch-table.md`）。

## 流程（照順序，每步都做）

1. **拿真資料，不拿印象。**
   ```bash
   python3 {SKILL_DIR}/scripts/dispatch-ratio.py --days 7
   python3 {PLUGIN_ROOT}/skills/agent-usage-report/report.py --days 7
   ```
   第一支算核心指標（萬用 agent 明確帶 model 的比例＋各 agent 實際模型分布），第二支算次數與休眠 agent。
2. **對照派工表找錯配。** 三種訊號：
   - 萬用 agent 帶 model 比例下滑：執行紀律問題，不動設定，提醒自己下週照表。
   - 某個專才 agent 產出連續被打回／重派：該升一級（sonnet 換 opus）。
   - 某個機械活 agent 連續一個月零失誤：可以降一級試（opus 換 sonnet）。
3. **休眠 agent 列 kill-switch 候選。** 30 天 0 次觸發就列出來，**是否砍掉由使用者決定**，你只列。
4. **給建議，不超過 3 行，一次只動一個設定。** 先寫「我建議 X，因為 Y」再列細節。同時改兩個變因會分不清是誰的功勞；動完觀察一週再動下一個。
5. **等使用者拍板。** 沒拍板前不改任何 frontmatter、不改 CLAUDE.md。
6. **決策留檔。** 使用者決定後，把「改了什麼、為什麼、觀察到什麼時候」寫進他慣用的記錄處（memory 或筆記）。下次回顧從那裡接，不從零想。
7. **重置計時。**
   ```bash
   bash {SKILL_DIR}/scripts/mark-reviewed.sh
   ```

`{SKILL_DIR}` 是本 SKILL.md 所在目錄；`{PLUGIN_ROOT}` 是它上兩層。

## 回報格式

先講結論（一句話：這週有沒有錯配），再貼指標數字，再給建議。不要把整份報表倒進對話。

## 誠實邊界（回報時要講）

- 比例只代表「有沒有選」，不代表「選得對不對」。選得對不對要看打回率，那是滯後指標。
- 資料只來自本機 transcript；被清掉的 session 算不到。
- dispatch-guard 是 fail-open：python3 不在或輸入解析失敗就放行。所以比例不會是 100% 靠 hook 撐出來的，剩下靠紀律。
