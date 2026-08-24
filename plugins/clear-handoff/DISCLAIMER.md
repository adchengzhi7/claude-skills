# 免責聲明 / Disclaimer

## 中文

本工具為個人生產力用途：在清空 Claude Code context 前，把工作狀態寫成本地筆記檔並產出續做提示。

**使用前請理解：**

1. **完全在本地端運作**
   所有 session note 都寫在使用者本機（`~/.claude/sessions/`），不傳送任何資料到第三方伺服器。

2. **secret 防護是紀律不是技術保證**
   skill 的指示要求「不記明文 secret」，但最終寫入內容由模型產生，使用者應自行檢視 note 內容，勿將含機密的 note 提交進版本控制或公開分享。

3. **無擔保**
   依 MIT 授權，本軟體「按現狀」提供，作者不對任何使用後果負責，包括但不限於筆記遺失、交接資訊不完整導致的工作中斷。

## English

This is a personal productivity tool: it packs your working state into a local session note and resume prompts before clearing Claude Code's context.

- Runs entirely locally; stores nothing on remote servers
- The "no plaintext secrets" rule is an instruction to the model, not a technical guarantee — review notes before sharing or committing them
- Provided "AS IS" under the MIT License with no warranty

## 通報

如使用本工具時遇到隱私 / 安全問題，請開 GitHub Issue 反映。
