#!/usr/bin/env python3
"""啟動 Session 辦公室。

  python3 run.py            開辦公室（http://127.0.0.1:8765）
  python3 run.py --demo     用示範資料開（做外觀包、截圖用；不讀任何真實對話）
  python3 run.py --once     只整理一次、把資料印出來就結束（排錯用）
"""
import argparse
import json
import os
import sys
import threading
import time
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from office import collect, config, server, tmuxio  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="Session 辦公室")
    ap.add_argument("--port", type=int, help="改用別的 port（預設看設定檔，沒設就是 8765）")
    ap.add_argument("--config", help="設定檔位置（預設 ~/.config/session-office/config.json）")
    ap.add_argument("--demo", action="store_true", help="用示範資料")
    ap.add_argument("--once", action="store_true", help="整理一次、印出來就結束")
    ap.add_argument("--open", action="store_true", help="啟動後順便開瀏覽器")
    args = ap.parse_args(argv)
    if os.name == "nt":
        # 判斷「程式還活著嗎」的做法在原生 Windows 上會對那個程式送 Ctrl+C 甚至把它結束掉，所以直接不跑
        print("不支援原生 Windows（請在 WSL 裡跑）。", file=sys.stderr)
        return 1
    if args.port is not None and not 1024 <= args.port <= 65535:
        print("--port 要是 1024～65535", file=sys.stderr)
        return 1

    cfg_dir = config.config_dir()
    cfg_path = args.config or os.path.join(cfg_dir, "config.json")
    try:
        cfg = config.load(cfg_path)
    except config.ConfigError as e:
        print("設定檔有錯（" + cfg_path + "）：" + str(e), file=sys.stderr)
        return 1
    office = server.Office(collect.default_paths(), cfg_path, os.path.join(config.state_dir(), "state.json"),
                           os.path.join(cfg_dir, "themes"), demo_mode=args.demo, tmux_bin=tmuxio.find_tmux())
    if args.once:
        snap = office.refresh()
        text = json.dumps(snap["data"] if snap["ok"] else {"error": snap["error"]}, ensure_ascii=False, indent=1)
        sys.stdout.write(text.encode("utf-8", "backslashreplace").decode("utf-8") + "\n")  # 落單的半個字元不能讓它印不出來
        return 0 if snap["ok"] else 1

    port = args.port or cfg["port"]
    try:
        httpd = server.make_server(office, port)
    except OSError as e:
        print("開不了 port " + str(port) + "（" + str(e) + "）。可能已經有一間辦公室在跑，或用 --port 換一個。", file=sys.stderr)
        return 1
    threading.Thread(target=office.loop, daemon=True).start()
    url = "http://127.0.0.1:" + str(port) + "/"
    print("Session 辦公室開在 " + url + ("（示範資料）" if args.demo else "") + "　按 Ctrl+C 關掉")
    if args.open:
        threading.Thread(target=lambda: (time.sleep(0.5), webbrowser.open(url)), daemon=True).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n關掉了")
    return 0


if __name__ == "__main__":
    sys.exit(main())
