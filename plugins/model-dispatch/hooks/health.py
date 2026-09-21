#!/usr/bin/env python3
"""
dispatch-guard 健康檢查（SessionStart）——防「閘門安靜地壞掉」。

背景：Claude Code 曾把派工工具從一個名字改成另一個，只認舊名字的閘門會在幾天內
幾乎沒擋、也不會有任何錯誤訊息，只有靠人回頭看數字才會發現。這支補兩道防線：

1. 看門狗：近 48 小時的對話紀錄裡「真的有派工」（任何工具名，只要輸入帶
   subagent_type），但閘門的打卡紀錄（見 dispatch-guard.py 的 punch()）一筆都
   沒有 → 警告閘門可能沒在跑。另外：派工用的工具名不在閘門監聽清單（Agent|Task）
   → 警告「又改名了」。
2. 金絲雀：Claude Code 版本跟上次不同 → 自動跑同資料夾的 test.sh，不過就警告。

一切正常時完全不出聲；有問題才輸出一行給主 Claude（會出現在開場 context）。
本身出錯一律安靜退出——健康檢查不能變成新的開場雜訊來源；上次成功跑的時間記在
STATE 裡，方便回顧看它有沒有在動。

不含任何個人路徑、帳號或客戶資料；預設用 $CLAUDE_PLUGIN_DATA，沒有就退到
~/.claude/plugin-data/model-dispatch/（跟 review-reminder.sh 同慣例）。
"""
import glob
import json
import os
import subprocess
import sys
import time

HOME = os.path.expanduser("~")
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("CLAUDE_PLUGIN_DATA") or os.path.join(HOME, ".claude/plugin-data/model-dispatch")
LOG = os.environ.get("DISPATCH_GUARD_LOG") or os.path.join(DATA_DIR, "dispatch-guard.jsonl")
STATE = os.path.join(DATA_DIR, "health-state.json")
TEST = os.path.join(HERE, "test.sh")
WATCHED = {"Agent", "Task"}
WINDOW = 48 * 3600
MIN_DISPATCH = 3


def load_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {}


def save_state(st):
    try:
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        json.dump(st, open(STATE, "w"), ensure_ascii=False)
    except Exception:
        pass


def recent_dispatches(since):
    n, names = 0, set()
    for f in glob.glob(os.path.join(HOME, ".claude/projects/*/*.jsonl")):
        try:
            if os.path.getmtime(f) < since:
                continue
            with open(f, errors="ignore") as fh:
                for line in fh:
                    if '"subagent_type"' not in line or '"tool_use"' not in line:
                        continue
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    ts = d.get("timestamp", "")
                    try:
                        t = time.mktime(time.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S")) - time.timezone
                    except Exception:
                        t = since
                    if t < since:
                        continue
                    for b in (d.get("message") or {}).get("content") or []:
                        if isinstance(b, dict) and b.get("type") == "tool_use" and isinstance(b.get("input"), dict) \
                                and "subagent_type" in b["input"]:
                            n += 1
                            names.add(b.get("name") or "?")
        except Exception:
            continue
    return n, names


def punches(since):
    c = 0
    try:
        with open(LOG) as fh:
            for line in fh:
                try:
                    if json.loads(line).get("ts", 0) >= since:
                        c += 1
                except Exception:
                    continue
    except FileNotFoundError:
        return 0
    return c


def main():
    warns = []
    st = load_state()
    now = time.time()

    # 金絲雀：Claude Code 版本變了就跑一次測試
    try:
        ver = subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        ver = ""
    if ver and ver != st.get("version") and os.path.isfile(TEST):
        try:
            r = subprocess.run(["bash", TEST], capture_output=True, text=True, timeout=60)
            if r.returncode != 0:
                last_line = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "無輸出"
                warns.append(f"Claude Code 更新成 {ver} 後，派工閘門的金絲雀測試沒過：{last_line}（跑 bash {TEST} 看細節）")
            else:
                st["version"] = ver
        except Exception as e:
            warns.append(f"派工閘門金絲雀測試跑不起來：{e}")

    # 看門狗：有派工卻沒打卡／工具又改名
    # 只看「打卡功能裝好之後」的派工，避免剛安裝時把舊派工當成沒打卡而誤報
    st.setdefault("installed_at", int(now))
    since = max(now - WINDOW, st["installed_at"])
    n, names = recent_dispatches(since)
    p = punches(since)
    unknown = sorted(names - WATCHED)
    if unknown:
        warns.append(f"派工工具出現新名字 {unknown}，派工閘門只監聽 Agent|Task——很可能又改名了，閘門擋不到（要改 settings.json 的 matcher 與 dispatch-guard.py）")
    if n >= MIN_DISPATCH and p == 0:
        warns.append(f"近 48 小時有 {n} 次派工，派工閘門卻 0 次打卡——閘門可能沒在跑（查 settings.json 的 PreToolUse matcher、跑 bash {TEST}）")

    st["last_ok_run"] = int(now)
    st["last_counts"] = {"dispatch_48h": n, "punch_48h": p}
    save_state(st)
    if warns:
        print("派工閘門健康檢查：" + "；".join(warns))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
