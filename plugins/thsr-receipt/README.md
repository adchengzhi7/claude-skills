# thsr-receipt

自動下載**台灣高鐵**購票證明 PDF 用於報帳，做成 [Claude Code](https://claude.com/claude-code) Skill / Plugin。

> 姊妹專案：[tra-receipt](../tra-receipt/)（台鐵）

## 它做什麼

在 Claude Code 裡丟一句：

```
下載高鐵購票證明：訂位代號 P5KW39C7，2026/04/15 台北→左營
```

或拖一張高鐵訂票確認 / 取票畫面截圖進來，PDF 自動落地：

```
~/Downloads/thsr_receipts/2026-04-15-台北-左營-P5KW39C7.pdf
```

## v0.1 適用範圍

- ✅ **磁票 / QR Code 紙票**（網路訂票後取票，自動售票機 / 超商 / 窗口取票）
- ⚠️ T Express 行動票證 → v0.2 再加（需要不同的 sub-tab）
- ❌ 回數票 / 定期票 → 不在範圍

## 跟台鐵的差別

| 項目 | 台鐵 (tra-receipt) | 高鐵 (thsr-receipt) |
|---|---|---|
| 認證方式 | 身分證 + 訂票代碼 | 訂位代號 / 車票號碼 |
| 身分證字號 | 從 Keychain | **不需要** |
| 必要資訊 | 1 個（訂票代碼）| 5 個（代號 + 日期 + 起訖 + 票種）|
| PDF 是否加密 | 否 | **是**，密碼 = 乘車日 YYYYMMDD |
| 下載次數限制 | 無 | 報稅扣抵證明只能下載 1 次 |

## CLI 用法

```bash
python3 ~/.claude/skills/thsr-receipt/scripts/download.py \
  --code P5KW39C7 \
  --date 2026-04-15 \
  --from 台北 \
  --to 左營
```

選項：

| 旗標 | 說明 |
|---|---|
| `--code` | 訂位代號（8 碼英數）OR 車票號碼（13 碼純數字），自動判斷 |
| `--date` | 乘車日期，YYYY-MM-DD |
| `--from`、`--to` | 起站 / 訖站，中文站名 |
| `--seat-type` | `reserved`（對號座，預設）/ `free`（自由座）|

合法車站（中文）：南港、台北、板橋、桃園、新竹、苗栗、台中、彰化、雲林、嘉義、台南、左營

## PDF 密碼

下載後的 PDF **有密碼保護**，密碼是**乘車日期的 8 位數字**（YYYYMMDD）。

例：`2026-04-15` → 密碼 `20260415`

腳本執行完會印出來提醒你。在 Preview / Adobe Reader 開啟時輸入即可。

如果要程式化解密，可以用 `qpdf`：

```bash
brew install qpdf
qpdf --decrypt --password=20260415 input.pdf output.pdf
```

## 限制（高鐵官方規定）

- 只能查**前一年到前一日**的資料
- 前一日的資料要等**乘車次日中午 12:00 後**才能查
- 報稅扣抵用的證明**只能下載一次**（要存好別丟）
- 票價為 0 的票無法提供本服務
- 自由座車票**只能用車票號碼查**，不能用訂位代號

## 隱私與安全

- 不需要身分證字號（跟台鐵不同），整個流程比 TRA 更不敏感
- 訂位代號 / 車票號碼**不寫入任何檔案**
- 連線都走 TLS，高鐵官方系統 (`ptis.thsrc.com.tw`)
- PDF 落本機 `~/Downloads/thsr_receipts/`，不上雲

## License

MIT — 同 root [LICENSE](../../LICENSE)
