# cloud-receipts

> Claude Code skill：從 Gmail 自動抓 SaaS 訂閱發票（Vercel / Supabase / Anthropic / Netlify）按月份歸檔。

跟 `uber-receipt` 同個 repo、同個 macOS Keychain 設計，互不衝突。

## ⚠️ 使用前請看 [DISCLAIMER.md](DISCLAIMER.md)

---

## 30 秒看它做什麼

跟 Claude 說「整理本月雲端發票」→

```
~/Downloads/cloud_receipts/
├── vercel/2026-04/
│   ├── 2026-04-09-Vercel-XXXX-YYYY-invoice.pdf
│   └── 2026-04-09-Vercel-XXXX-YYYY-receipt.pdf
├── supabase/2026-04/
├── anthropic/2026-04/
└── netlify/2026-04/
```

每張 invoice 收 2 個 PDF（Stripe 標準：Invoice + Receipt 各一）。

---

## 安裝（macOS）

```bash
# 1. cp 到 skills 目錄（隨 ~/.claude/ repo 一起 sync 即可）
# 2. 跑 wizard（沿用 uber-receipt 的 Gmail 設定流程）
python3 ~/.claude/skills/cloud-receipts/scripts/main.py --setup

# 或手動：
EMAIL='your@gmail.com'
python3 -c "
import sys; sys.path.insert(0, '$HOME/.claude/skills/cloud-receipts/scripts')
from base.gmail_fetcher import add_account; add_account('$EMAIL')
"
security add-generic-password -a "$EMAIL" -s 'cloud-receipts-gmail' -w 'XXXX XXXX XXXX XXXX' -U
```

---

## 用法

跟 Claude 說：
- 「整理本月雲端發票」 / 「抓 Vercel invoice」 / 「Supabase 報帳」

或直接 CLI：
```bash
python3 .../main.py --list                        # 列出可用 provider + 帳號
python3 .../main.py all --from-gmail              # 全部 provider 抓
python3 .../main.py vercel --from-gmail           # 單一 provider
python3 .../main.py supabase --from-gmail --dry-run --since 2026-01-01
```

---

## 支援的 Provider

| Provider | sender | 模式 |
|---|---|---|
| **Vercel** | `invoice+statements@vercel.com` | Stripe attachment（每月 2 個 PDF） |
| **Supabase** | `invoice+statements@supabase.com` | 同 |
| **Anthropic** (Claude) | `invoice+statements@mail.anthropic.com` | 同 |
| **Netlify** | `noreply@netlify.com` | 同 |

未來若要加：
- GitHub / OpenAI / Render / Fly.io / Cloudflare / AWS / GCP …
- 只要 ~5 行 config，因為大多都用 Stripe 標準寄件模板

---

## 加新 provider 自己改

`scripts/providers/stripe_style.py`：
```python
class GitHubProvider(StripeAttachmentProvider):
    name = "github"
    display_name = "GitHub"
    sender = "billing@github.com"
```

`scripts/providers/__init__.py` 加 `REGISTRY["github"] = GitHubProvider`，完成。

---

## 多 Gmail 帳號

支援 N 個 Gmail 帳號，每個獨立 App Password。例如：
- `personal@example.com` 收 Anthropic invoice
- `dev@example.com` 收 Vercel / Supabase invoice
- 一個指令掃所有帳號 + 全部 provider

`~/.config/receipts/gmail.json`：
```json
{
  "accounts": [
    {"email": "you@example.com", "label": "personal"},
    {"email": "dev@example.com", "label": "dev"}
  ]
}
```

每個 provider 可指定 `preferred_accounts` 限制只在某些帳號搜尋。預設全帳號掃。

---

## 檔案位置

| 用途 | 路徑 |
|---|---|
| Skill 程式 | `~/.claude/skills/cloud-receipts/` |
| 公司清單（共用） | `~/.config/receipts/companies.json` |
| Gmail 帳號清單 | `~/.config/receipts/gmail.json` |
| App Password | macOS Keychain (`cloud-receipts-gmail`) |
| 已處理紀錄 | `~/.config/receipts/<provider>-processed.json` |
| **歸檔 PDF** | `~/Downloads/cloud_receipts/<provider>/YYYY-MM/` |

---

## 跟 `uber-receipt` 怎麼共存

兩個 skill 互補：
- `uber-receipt` — 計程車行程，需 Playwright 登入 dashboard 下載
- `cloud-receipts` — 雲訂閱，IMAP 抓附件即可

兩者：
- 共用 `~/.config/receipts/companies.json`、`gmail.json`、Keychain
- 各自 processed log（不衝突）
- Claude 觸發詞不同（「Uber 收據」vs「雲端發票」）

---

## 授權

[MIT](LICENSE)（同 [DISCLAIMER](DISCLAIMER.md)）。
