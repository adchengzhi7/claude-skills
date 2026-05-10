# 免責聲明 / Disclaimer

## 中文

本工具是個人用途，協助使用者整理**自己**的 Uber 行程紀錄與電子發票，作為費用報帳憑證。

**使用前請理解：**

1. **與 Uber、Google 無關聯**
   本專案並非由 Uber Technologies, Inc.、優步福爾摩沙股份有限公司、Google LLC 或其關聯公司提供、認可、贊助或支持。

2. **服務條款風險自行承擔**
   Uber 服務條款可能對自動化方式存取服務有限制。本工具僅在使用者已登入個人帳號的瀏覽器 session 下運作，但仍存在被 Uber 視為「不正常存取」並影響帳號的風險。建議：
   - 不要排程跑（`cron` / `launchd`）
   - 不要短時間連抓大量行程
   - 一般月底整理一次即可
   - 若帳號收到警告，立即停用

3. **不收集任何資料**
   本工具完全在本地端運作，不傳送任何資料到第三方伺服器。所有 credentials（Gmail App Password、Uber session cookies）都儲存在使用者本機的 Keychain / 私人目錄。

4. **無擔保**
   依 MIT 授權，本軟體「按現狀」提供，作者不對任何使用後果負責，包括但不限於資料遺失、帳號管制、報帳失敗等。

5. **報帳合規性**
   本工具產生的 PDF 是否符合貴公司財務政策或稅務規範，請自行向會計、財務或稅務專業人員確認。台灣多元計程車車資（行程費用部分）系統制度上不開立統一發票；本工具僅能取得 Uber Formosa 開立的處理費電子發票（XML / PDF），並非完整核銷憑證。

6. **遵守當地法律**
   使用者有責任確保其使用方式符合中華民國個人資料保護法、稅捐稽徵法、所得稅法及其他相關規範。

## English

This tool is a personal-use utility for organizing **your own** Uber trip records and electronic receipts.

- Not affiliated with, endorsed by, or sponsored by Uber, Google, or any subsidiary
- Use at your own risk; Uber's Terms of Service may restrict automated access
- Stores no data on remote servers; everything runs locally
- Provided "AS IS" under MIT License with no warranty
- Tax / accounting compliance is the user's responsibility — consult a professional

## 通報

如使用本工具時遇到隱私 / 安全 / 法律問題，請開 GitHub Issue 反映。
