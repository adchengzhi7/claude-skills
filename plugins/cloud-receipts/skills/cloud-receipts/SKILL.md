---
name: cloud-receipts
description: 從 Gmail 自動抓 SaaS 訂閱發票（Vercel / Supabase / Anthropic / Netlify 等）並按月份歸檔。當使用者說「整理 Vercel invoice」「Supabase 報帳」「整理雲端服務發票」「抓本月雲端訂閱收據」時觸發。支援多 Gmail 帳號、provider plugin 架構，每個 provider 是 ~10 行 config。和姊妹 skill uber-receipt / thsr-receipt 共用 ~/.config/receipts/companies.json。
---

# cloud-receipts — Claude 操作手冊

把雲服務（Vercel / Supabase / Anthropic / Netlify 等）的月訂閱發票從 Gmail **自動抓附件 PDF**、歸檔到 `~/Downloads/cloud_receipts/<provider>/YYYY-MM/`。

跟 `uber-receipt` 不同的地方：
- ❌ 不需要 Playwright 登入（信件直接含 PDF 附件）
- ✅ Stripe 標準寄件人模式：`invoice+statements@<provider>.com`
- ✅ 一個 base class（`StripeAttachmentProvider`）支援所有 Stripe-style provider，加新 provider 只要 5 行 config

---

## Phase 0：環境檢查

```bash
which python3 || echo "❌ 缺 python3"
python3 ~/.claude/skills/cloud-receipts/scripts/main.py --list
```

`--list` 會印：
- 已知 provider（vercel / supabase / anthropic / netlify）
- companies.json 內容（共用）
- Gmail accounts 設定狀況

---

## Phase 1：Gmail 帳號設定（多帳號支援）

設定流程跟 uber-receipt 共用 keychain（service: `cloud-receipts-gmail`），舊的 `uber-receipt-gmail` 會自動 fallback。

加新 Gmail 帳號：
```bash
EMAIL='someone@gmail.com'

# 1. 寫入 gmail.json
python3 -c "
import sys; sys.path.insert(0, '$HOME/.claude/skills/cloud-receipts/scripts')
from base.gmail_fetcher import add_account
add_account('$EMAIL', label='dev')
"

# 2. 存 App Password（先在 https://myaccount.google.com/apppasswords 建立）
security add-generic-password -a "$EMAIL" -s 'cloud-receipts-gmail' -w 'XXXX XXXX XXXX XXXX' -U
```

`gmail.json` 格式：
```json
{
  "accounts": [
    {"email": "you@example.com", "label": "personal"},
    {"email": "dev@example.com", "label": "dev"}
  ]
}
```

---

## Phase 2：抓 + 歸檔

跑全部 provider：
```bash
python3 ~/.claude/skills/cloud-receipts/scripts/main.py all --from-gmail
```

跑單一 provider：
```bash
python3 .../main.py vercel --from-gmail
python3 .../main.py supabase --from-gmail
python3 .../main.py anthropic --from-gmail
python3 .../main.py netlify --from-gmail
```

選項：
- `--since YYYY-MM-DD` — 只抓這日期之後的（預設 180 天）
- `--refetch` — 略過 processed log 重抓
- `--dry-run` — 試跑不寫檔
- `--overwrite` — 目標檔已存在強制覆蓋

歸檔位置：
```
~/Downloads/cloud_receipts/
├── vercel/
│   └── 2026-04/
│       ├── 2026-04-09-Vercel-XXXX-YYYY-invoice.pdf
│       └── 2026-04-09-Vercel-XXXX-YYYY-receipt.pdf
├── supabase/
├── anthropic/
└── netlify/
```

---

## Phase 3：擴增新 provider（給未來的 Claude）

新 provider 如果是 Stripe-style attachment：

```python
# providers/stripe_style.py
class GitHubProvider(StripeAttachmentProvider):
    name = "github"
    display_name = "GitHub"
    sender = "billing@github.com"
```

然後 `providers/__init__.py` 加註冊：
```python
REGISTRY["github"] = GitHubProvider
```

完成。零其他改動，自動支援 `python3 main.py github --from-gmail`。

非 Stripe 模式（信件無附件、需登入下載）→ 繼承 `DashboardProvider`，覆寫 `parse()`，類似 uber-receipt 的做法。

---

## 錯誤 cookbook

| 錯誤 | 原因 | 修法 |
|---|---|---|
| `Gmail 連線資訊未設定` | gmail.json 不存在或無 keychain 密碼 | 跑 Phase 1 設定流程 |
| `Authentication failed` | App Password 錯，或 Workspace admin 禁用 | 重建 App Password / 換個人 Gmail |
| 抓到 0 張 | sender filter 錯，或 user 是 free tier | 確認 sender 為 `invoice+statements@<domain>` |
| `無附件，略過` | 該封不是 invoice 信件（可能是 reminder / payment failed）| 正常行為，跳過即可 |
| 解析錯誤 | 信件格式可能變了 | 印 raw text，更新 regex |

---

## 不在範圍

| 別人問你 | 你回 |
|---|---|
| Uber 行程整理 | 用姊妹 skill `uber-receipt` |
| 高鐵 / 台鐵車票 | `thsr-receipt` / `tra-receipt` |
| 把雲訂閱發票打統編 | 美國公司不開 TW 統一發票，做不到 |
| 美元換台幣 | 看信用卡帳單，這個 skill 不處理匯率 |

---

## 快速指令

```bash
python3 ~/.claude/skills/cloud-receipts/scripts/main.py --list           # 列 provider + accounts
python3 .../main.py all --from-gmail --dry-run                            # 全 provider 試跑
python3 .../main.py vercel --from-gmail --since 2026-01-01                # 單 provider 抓特定區間
python3 .../main.py supabase --from-gmail --refetch                       # 略過 processed log
```
