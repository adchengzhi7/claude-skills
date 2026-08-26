#!/usr/bin/env bash
# 站台管理：init / start / stop / status / install / uninstall
set -euo pipefail
. "$(cd "$(dirname "$0")" && pwd)/_config.sh"

PLIST_LABEL="local.previews"
PLIST="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"

usage() {
  cat <<USAGE
用法：serve.sh <指令>

  init       建立站台資料夾與首頁（第一次架站用；已存在不會覆蓋）
  start      啟動站台（前景程序丟到背景）
  stop       停止站台
  status     看站台活著沒、綁在哪
  install    裝成開機自動啟動（macOS launchd）
  uninstall  移除開機自動啟動

目前設定：$PREVIEWS_DIR  →  $BASE_URL
USAGE
}

alive() { curl -s -o /dev/null --max-time 2 "$BASE_URL/"; }

cmd_init() {
  mkdir -p "$PREVIEWS_DIR"
  if [ -f "$PREVIEWS_DIR/index.html" ]; then
    echo "首頁已存在，沒有覆蓋：$PREVIEWS_DIR/index.html"
  else
    python3 - "$SKILL_DIR/templates/index.html" "$PREVIEWS_DIR/index.html" "$PREVIEWS_TITLE" <<'PY'
import sys
src, dst, title = sys.argv[1], sys.argv[2], sys.argv[3]
s = open(src, encoding="utf-8").read().replace("{{TITLE}}", title)
open(dst, "w", encoding="utf-8").write(s)
PY
    echo "已建立首頁：$PREVIEWS_DIR/index.html"
  fi
  python3 "$SKILL_DIR/scripts/gen-pages-index.py" "$PREVIEWS_DIR"
  echo "接著跑：serve.sh start（或 serve.sh install 讓它開機自動起來）"
}

cmd_start() {
  if alive; then echo "站台已經在跑：$BASE_URL"; return; fi
  nohup python3 -m http.server "$PREVIEWS_PORT" \
    --bind "$PREVIEWS_BIND_IP" --directory "$PREVIEWS_DIR" \
    >>"$PREVIEWS_DIR/.server.log" 2>>"$PREVIEWS_DIR/.server.err" &
  disown || true
  sleep 1.5
  alive && echo "✓ 站台已啟動：$BASE_URL" \
        || die "啟動失敗，看 $PREVIEWS_DIR/.server.err"
}

cmd_stop() {
  pkill -f "http.server $PREVIEWS_PORT --bind $PREVIEWS_BIND_IP" 2>/dev/null \
    && echo "已停止" || echo "沒找到在跑的站台"
}

cmd_status() {
  echo "資料夾：$PREVIEWS_DIR"
  echo "網址　：$BASE_URL"
  alive && echo "狀態　：活著" || echo "狀態　：沒回應"
  if [ -f "$PLIST" ]; then
    echo "開機自動啟動：已安裝（${PLIST_LABEL}）"
  else
    echo "開機自動啟動：本 skill 沒裝過"
    echo "  （若站台是活著的，代表你另有一套在顧它——別重複安裝，會兩個程序搶同一個 port）"
  fi
  echo
  echo "存取紀錄在 $PREVIEWS_DIR/.server.err"
  echo "（不是 .server.log —— python 的 http.server 把存取紀錄寫到 stderr）"
}

cmd_install() {
  mkdir -p "$HOME/Library/LaunchAgents"
  cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>${PLIST_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>-m</string><string>http.server</string>
    <string>${PREVIEWS_PORT}</string>
    <string>--bind</string><string>${PREVIEWS_BIND_IP}</string>
    <string>--directory</string><string>${PREVIEWS_DIR}</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>${PREVIEWS_DIR}/.server.log</string>
  <key>StandardErrorPath</key><string>${PREVIEWS_DIR}/.server.err</string>
</dict>
</plist>
PLISTEOF
  launchctl unload "$PLIST" 2>/dev/null || true
  launchctl load "$PLIST"
  sleep 1.5
  alive && echo "✓ 已安裝並啟動：$BASE_URL" || echo "⚠ 已安裝但沒回應，看 $PREVIEWS_DIR/.server.err"
  echo
  echo "注意：Tailscale 要先連上，這個 IP 才存在。開機順序若讓站台先起來，"
  echo "launchd 的 KeepAlive 會一直重試，等 Tailscale 上線後就會成功。"
}

cmd_uninstall() {
  [ -f "$PLIST" ] || { echo "本來就沒安裝"; return; }
  launchctl unload "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"
  echo "已移除開機自動啟動（站台本身沒停，要停跑 serve.sh stop）"
}

case "${1:-}" in
  init) cmd_init ;; start) cmd_start ;; stop) cmd_stop ;;
  status) cmd_status ;; install) cmd_install ;; uninstall) cmd_uninstall ;;
  *) usage ;;
esac
