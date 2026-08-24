---
name: google-bills
description: 從 Gmail 抓 Google Payments 寄出的帳單 PDF（Google Workspace + Google Cloud Platform）。當使用者說「整理 Google 帳單」「抓 Google Cloud invoice」「Google Workspace 報帳」「整理 GCP 帳單」時觸發。重用 cloud-receipts 的 base 模組。
---

# google-bills

> 路徑說明：`{SKILL_DIR}` ＝ 本 skill 的安裝目錄（skill 載入時系統會標示 base directory；手動裝在 `~/.claude/skills/` 的話就是那裡，plugin 安裝則在 plugin 快取目錄）。


從 Gmail 抓 Google Payments（payments-noreply）的帳單 PDF，依 subject 自動分流到 Workspace / GCP 兩個資料夾。

## 用法

```bash
# 抓最近 6 個月的 Google 帳單，依 subject 分流歸檔
python3 {SKILL_DIR}/scripts/main.py

# 抓全部歷史
python3 {SKILL_DIR}/scripts/main.py --since 2024-01-01 --refetch

# Dry-run
python3 {SKILL_DIR}/scripts/main.py --dry-run
```

## 歸檔位置

```
~/Downloads/google_bills/
├── workspace/2026-04/<filename-from-attachment>.pdf
└── gcp/2026-04/<filename-from-attachment>.pdf
```

PDF 檔名沿用 Google 給的（純數字 invoice ID，如 `5472942755.pdf`）。

## 設計

- 重用 `cloud-receipts/scripts/base/`（gmail_fetcher / organize 框架）
- 寄件人：Google Payments 服務信箱 + subject regex 分流 Workspace vs GCP
- 每個 sub-product 獨立 processed log（避免重抓）

## 前置需求

跟 cloud-receipts 一樣，需要先用 cloud-receipts wizard 設定 Gmail App Password：

```bash
python3 <cloud-receipts 的 SKILL_DIR>/scripts/main.py --setup
```

## 觸發詞（給 Claude）

- 「整理 Google 帳單」
- 「抓 Google Cloud invoice」
- 「Google Workspace 報帳」
- 「整理 GCP 帳單」
