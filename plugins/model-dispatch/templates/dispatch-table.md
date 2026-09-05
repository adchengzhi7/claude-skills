# 派工表範本（貼進你的 CLAUDE.md，照自己的模型與預算改）

## 模型派工

- **主 session 模型不切換**（中途切主模型會打爆 prompt cache）；分流一律靠子 agent 派工時指定 model
- 判斷軸兩條：**有驗證兜底**（CI / 測試 / E2E 會抓錯）→ 便宜模型放心跑；**做歪代價高**（碰錢 / prod / 不可逆 / 跨模組）→ 貴模型

| 任務形狀 | model | effort |
|---|---|---|
| 搜 code / 讀檔盤點 / 找檔案 | haiku 或 sonnet | low |
| 例行 rollout：merge、盯部署、跑驗證、機械改寫 | sonnet | low–medium |
| 寫功能 / 修 bug（有測試兜底） | sonnet | medium |
| code review / 深度除錯 / schema 設計 | opus | high |
| 規劃、架構決策、方案設計 | inherit（跟主 session） | high+ |

- **Cascade 原則**：預設便宜、失敗才升級。同一 agent 產出連續被打回 → 升一級；連續一個月零失誤的機械活 → 降一級試。**一次只動一個設定，觀察一週再動下一個**
- 具名專才 agent 的模型寫在各自 `agents/*.md` 的 frontmatter（範本見 `agent-frontmatter.md`）
- 機器層護欄：`dispatch-guard` hook 擋「派 general-purpose 卻沒指定 model」——不做語意猜測，只逼你當場選
