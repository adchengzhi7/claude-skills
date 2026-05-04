#!/usr/bin/env bash
# tra-receipt 安裝腳本
# 用途：裝齊依賴（playwright + chromium + poppler）並引導使用者把身分證/居留證號存進 Keychain

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

info()  { printf "${GREEN}[OK]${NC} %s\n" "$*"; }
warn()  { printf "${YELLOW}[..]${NC} %s\n" "$*"; }
err()   { printf "${RED}[!!]${NC} %s\n" "$*" >&2; }

# 1. 環境檢查
if [[ "$(uname -s)" != "Darwin" ]]; then
  err "本 skill 目前僅支援 macOS（用了 Keychain 與 open 指令）"
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  err "找不到 python3，請先 brew install python"
  exit 1
fi

if ! command -v brew >/dev/null 2>&1; then
  err "找不到 Homebrew，請先安裝：https://brew.sh"
  exit 1
fi

info "偵測到 macOS、python3、Homebrew"

# 2. 裝 poppler（提供 pdftotext）
if ! command -v pdftotext >/dev/null 2>&1; then
  warn "安裝 poppler（提供 pdftotext，用來抽 PDF metadata）"
  brew install poppler
else
  info "poppler/pdftotext 已安裝"
fi

# 3. 裝 playwright
if ! python3 -c "import playwright" >/dev/null 2>&1; then
  warn "安裝 playwright（pip3 --break-system-packages）"
  pip3 install --break-system-packages playwright
else
  info "playwright 已安裝"
fi

# 4. 裝 chromium browser
warn "確認 / 下載 chromium（約 150MB，第一次裝會比較久）"
python3 -m playwright install chromium

# 5. 安裝 skill 到 ~/.claude/skills/
SKILL_SRC="$(cd "$(dirname "$0")/skills/tra-receipt" && pwd)"
SKILL_DST="$HOME/.claude/skills/tra-receipt"

if [[ -d "$SKILL_DST" ]]; then
  warn "$SKILL_DST 已存在，覆蓋"
fi
mkdir -p "$HOME/.claude/skills"
rm -rf "$SKILL_DST"
cp -R "$SKILL_SRC" "$SKILL_DST"
info "skill 已安裝到 $SKILL_DST"

# 6. 提示 Keychain 設定（不幫使用者打 ID）
echo
if security find-generic-password -a "$USER" -s "tra-id" -w >/dev/null 2>&1; then
  info "Keychain 已有 tra-id（如要更新請手動執行 security delete-generic-password ...）"
else
  cat <<EOF
${YELLOW}[!]${NC} 還沒在 Keychain 設定身分證 / 居留證統一證號。請執行：

   ${GREEN}security add-generic-password -a "\$USER" -s "tra-id" -w "你的身分證或居留證號"${NC}

格式：
  - 台灣身分證：1 英文 + 9 數字（第 2 碼是 1 或 2），例 A123456789
  - 居留證統一證號：1 英文 + 9 數字（第 2 碼是 8 或 9），例 A800000014
EOF
fi

# 7. 完成提示
echo
info "安裝完成 🎉"
echo "用法：在 Claude Code 裡丟一句「下載 3333333 的台鐵購票證明」即可。"
echo "PDF 會落到 ~/Downloads/tra_receipts/{乘車日}-{起站}-{訖站}-{票號}.pdf"
