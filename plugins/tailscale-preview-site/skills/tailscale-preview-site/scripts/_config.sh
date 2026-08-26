#!/usr/bin/env bash
# 共用設定載入 —— 所有腳本 source 這支，不要各自寫死路徑。
#
# 找設定的順序：
#   1) $PREVIEWS_CONFIG 指定的檔
#   2) ~/.config/previews/config.env
#   3) 這個 skill 目錄下的 config.env
# 都找不到就給明確指示，不猜。

_here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_skill_dir="$(dirname "$_here")"

die() { echo "✗ $*" >&2; exit 1; }

CONFIG=""
for c in "${PREVIEWS_CONFIG:-}" "$HOME/.config/previews/config.env" "$_skill_dir/config.env"; do
  [ -n "$c" ] && [ -f "$c" ] && { CONFIG="$c"; break; }
done

if [ -z "$CONFIG" ]; then
  cat >&2 <<MSG
✗ 找不到設定檔。

  先複製範例再改成你的值：
    mkdir -p ~/.config/previews
    cp "$_skill_dir/config.example.env" ~/.config/previews/config.env
    \$EDITOR ~/.config/previews/config.env

  最少要填 PREVIEWS_BIND_IP（用 \`tailscale ip -4\` 查你的 Tailscale IP）。
  完整步驟見 $_skill_dir/SETUP.md
MSG
  exit 1
fi

# shellcheck disable=SC1090
. "$CONFIG"

PREVIEWS_DIR="${PREVIEWS_DIR:-$HOME/previews}"
PREVIEWS_DIR="${PREVIEWS_DIR/#\~/$HOME}"
PREVIEWS_PORT="${PREVIEWS_PORT:-8787}"
PREVIEWS_TITLE="${PREVIEWS_TITLE:-預覽清單}"
PREVIEWS_HOSTNAME_PREFIX="${PREVIEWS_HOSTNAME_PREFIX:-}"
PREVIEWS_DECISION_REGEX="${PREVIEWS_DECISION_REGEX:-}"

[ -n "${PREVIEWS_BIND_IP:-}" ] || die "設定檔沒有 PREVIEWS_BIND_IP（${CONFIG}）"

# 綁 IP 的護欄：這個站沒有登入機制，靠「只有 Tailscale 網路連得到」當唯一防線。
# 綁 0.0.0.0 或 127 以外的公開介面會讓同一個區網的人也連得進來。
case "$PREVIEWS_BIND_IP" in
  100.*) ;;
  127.0.0.1|localhost) ;;
  *) die "PREVIEWS_BIND_IP=$PREVIEWS_BIND_IP 不是 Tailscale IP（100.x.y.z）。
   這個站沒有登入機制，只靠綁定 Tailscale IP 當防線。
   綁 0.0.0.0 等於對整個區網開放。用 \`tailscale ip -4\` 查正確的 IP。
   （真的要本機測試可以填 127.0.0.1）" ;;
esac

BASE_URL="http://${PREVIEWS_BIND_IP}:${PREVIEWS_PORT}"
SKILL_DIR="$_skill_dir"
