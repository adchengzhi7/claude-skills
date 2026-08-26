#!/usr/bin/env bash
# 把一份 HTML 發佈到預覽站。
#
# 用法：
#   publish.sh <檔>.html [--title "標題"] [--desc "一句摘要"] [--meta "日期 · 專案 · 狀態"] [--also <附件>]...
#
# 行為：檢查機器 → 清洗檔名 → 複製進站台資料夾 → 首頁插入/更新該檔的卡片
#       → 重建全站頁面清單 → 確認站台活著（掉了自動重開）→ 印出網址
set -euo pipefail
. "$(cd "$(dirname "$0")" && pwd)/_config.sh"

FILE="" TITLE="" DESC="" META=""
ALSO=()
while [ $# -gt 0 ]; do
  case "$1" in
    --title) TITLE="${2:-}"; shift 2 ;;
    --desc)  DESC="${2:-}";  shift 2 ;;
    --meta)  META="${2:-}";  shift 2 ;;
    --also)  ALSO+=("${2:-}"); shift 2 ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) [ -z "$FILE" ] && FILE="$1" || die "多餘參數：$1"; shift ;;
  esac
done

[ -n "$FILE" ] || die "用法：publish.sh <檔>.html [--title ...] [--desc ...] [--meta ...] [--also 附件]"
[ -f "$FILE" ] || die "檔案不存在：$FILE"
case "$FILE" in *.html|*.htm) ;; *) die "只收 .html（其他檔用 --also 當附件帶）" ;; esac

# 1) 站台只在某一台機器上；不在就明講怎麼辦，不硬做
if [ -n "$PREVIEWS_HOSTNAME_PREFIX" ]; then
  case "$(hostname)" in
    "$PREVIEWS_HOSTNAME_PREFIX"*) ;;
    *) die "這台不是站台所在的機器（設定要求 hostname 以 $PREVIEWS_HOSTNAME_PREFIX 開頭）。
   先把檔案送到那台的 $PREVIEWS_DIR 再跑。" ;;
  esac
fi

mkdir -p "$PREVIEWS_DIR"

# 1.5) 決策區檢查（選配，只警告不擋）
# 為什麼要有這個：報告最常見的失敗不是寫錯，是「列了一堆面向但沒說要決定什麼」，
# 讀的人得自己找重點。這裡不判斷內容好壞，只確認有沒有一段明講球在誰那裡。
if [ -n "$PREVIEWS_DECISION_REGEX" ] && ! grep -qE "$PREVIEWS_DECISION_REGEX" "$FILE"; then
  echo "⚠ 這份沒有「決策區」——讀的人要自己找『我要決定什麼』。" >&2
  echo "  （純參考資料類的頁面可忽略，發佈照常進行）" >&2
fi

# 2) 檔名清洗：URL 不收空格
name="$(basename "$FILE")"
name="${name// /-}"
[ "$(cd "$(dirname "$FILE")" && pwd)/$(basename "$FILE")" = "$PREVIEWS_DIR/$name" ] \
  && die "來源就在站台資料夾裡（${PREVIEWS_DIR}）。
   請把稿子放在別處再發佈——否則複製步驟會失敗，頁面雖然打得開但首頁不會出現卡片。"
cp "$FILE" "$PREVIEWS_DIR/$name"

# 防中文亂碼：簡易 HTTP 伺服器送 text/html 不帶 charset，
# HTML 若沒宣告編碼，瀏覽器會猜錯 → 中文變亂碼。沒宣告就自動補。
if ! grep -qi 'charset' "$PREVIEWS_DIR/$name"; then
  printf '<meta charset="utf-8">\n%s' "$(cat "$PREVIEWS_DIR/$name")" > "$PREVIEWS_DIR/$name.tmp" \
    && mv "$PREVIEWS_DIR/$name.tmp" "$PREVIEWS_DIR/$name"
fi

for extra in "${ALSO[@]+"${ALSO[@]}"}"; do
  [ -f "$extra" ] || die "附件不存在：$extra"
  ename="$(basename "$extra")"
  cp "$extra" "$PREVIEWS_DIR/${ename// /-}"
  echo "  附件 → $BASE_URL/${ename// /-}"
done

# 3) 首頁插入/更新卡片（手工策展清單：只動自己這張卡，其餘一律不碰）
INDEX="$PREVIEWS_DIR/index.html"
if [ -f "$INDEX" ]; then
  action="$(python3 "$SKILL_DIR/scripts/upsert_card.py" "$INDEX" "$name" "$TITLE" "$DESC" "$META")"
  echo "  首頁：$action"
else
  echo "  首頁還沒建立，先跑：$SKILL_DIR/scripts/serve.sh init" >&2
fi

# 3.5) 重建全站頁面清單（給首頁的搜尋與「未分類頁面」區塊用）
python3 "$SKILL_DIR/scripts/gen-pages-index.py" "$PREVIEWS_DIR" >/dev/null 2>&1 \
  && echo "  頁面清單：已更新" || echo "  ⚠ 頁面清單更新失敗（不影響發佈）" >&2

# 4) 站台健康檢查，掉了重開
if ! curl -s -o /dev/null --max-time 2 "$BASE_URL/"; then
  echo "  站台沒回應，重開中…"
  "$SKILL_DIR/scripts/serve.sh" start >/dev/null 2>&1 || true
  sleep 1.5
  curl -s -o /dev/null --max-time 3 "$BASE_URL/" \
    || die "站台重開失敗，看 $PREVIEWS_DIR/.server.err"
  echo "  站台已重開"
fi

echo "✓ $BASE_URL/$name"
