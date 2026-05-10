# google-bills

> Claude Code skill：從 Gmail 自動抓 Google Workspace + Google Cloud Platform 帳單 PDF，按 product/月份分類歸檔。

跟 `cloud-receipts` 共用 Gmail / Keychain 設定。

## ⚠️ 使用前請看 [DISCLAIMER.md](DISCLAIMER.md)

## 30 秒看它做什麼

跟 Claude 說「整理 Google 帳單」→

```
~/Downloads/google_bills/
├── workspace/2026-04/<invoice-id>.pdf
└── gcp/2026-04/<invoice-id>.pdf
```

PDF 檔名是 Google 內部 invoice ID（如 `5564799187.pdf`，可在 Google Workspace 後台對到）。

## 安裝

```bash
# 1. 先確保 cloud-receipts 已設定 Gmail（共用 keychain）
python3 ~/.claude/skills/cloud-receipts/scripts/main.py --list

# 2. 跑就好
python3 ~/.claude/skills/google-bills/scripts/main.py
```

## 用法

```bash
# 預設抓 180 天
python3 .../main.py

# 抓特定區間
python3 .../main.py --since 2026-01-01

# 重抓（略過 processed log）
python3 .../main.py --since 2026-01-01 --refetch

# 試跑不寫檔
python3 .../main.py --dry-run
```

## 分類規則

| Subject 含 | 分到 |
|---|---|
| `Google Workspace` | `workspace/` |
| `Google Cloud Platform` / `GCP` / `APIs` | `gcp/` |
| 其他 | `other/` |

## 多帳號

支援多 Gmail 帳號（沿用 cloud-receipts 的 `~/.config/receipts/gmail.json`）。所有帳號的 Google 帳單都會掃。

## 跟 cloud-receipts 為什麼分開

- `cloud-receipts`: 一個 sender = 一個產品（Stripe 標準）
- `google-bills`: **一個 sender 涵蓋多個產品**，需 subject 分類 — 模型不同

## 授權

[MIT](LICENSE)
