"""把 Claude Code 自己記的程式清單整理成辦公室要的一份資料。

Claude Code 每個執行中的程式都會寫一份 ~/.claude/sessions/<pid>.json：sessionId、資料夾、在哪個 tmux pane、
status（busy＝正在做事；waiting＝停下來等你；idle＝停著；shell＝停著但有背景指令開著）。這是唯一的必要來源，
其他（對話紀錄、tmux、Moshi）都是拿來補細節的。這裡只讀不寫 Claude Code 的任何東西。
"""
import glob
import json
import math
import os
import re

from . import moshi, tmuxio, transcript

STATE_VERSION = 1
KEEP_ENDED_SECONDS = 12 * 3600   # 已關閉的只留最近 12 小時
# 顯示「執行中」但這麼久完全沒寫入（對話紀錄＋派出去的 agent 都沒動）＝多半卡住了。
# 等背景工作／長時間監看會合法地安靜很久，所以門檻放一小時；API 串流卡死也長這樣，所以不能完全不判
STUCK_SECONDS = 60 * 60
# 「做到一半當掉」只在我們一直盯著的時候才判：上次看到它還在忙、而且就是這兩分鐘內的事。
# 辦公室關了半天再打開，只知道「上次看到在忙」，中間可能早就正常做完離開了，那不能叫當掉
CRASH_WATCH_SECONDS = 120
QUESTION_TOOLS = ("AskUserQuestion", "ExitPlanMode")
SID_RE = re.compile(r"[A-Za-z0-9-]{8,64}")  # 用 fullmatch 比對
IDLE_STATUSES = ("idle", "shell")
# 剛啟動的 session 有一小段時間還沒寫 status。超過這段時間還沒有，就不是「還沒寫」而是「格式變了」，要講出來
STARTUP_GRACE_SECONDS = 120
# 不寫 status 的 session（agent／SDK 開的）只能看對話紀錄最近有沒有在寫來猜它在不在忙
RECENT_WRITE_SECONDS = 120
# 沒有人坐在前面的 session（排程、腳本用 `claude -p` 跑的）開超過這麼久才畫出來：
# 幾秒就結束的那種每幾分鐘來一個，全畫出來只會讓工作區一直閃
HEADLESS_MIN_AGE_SECONDS = 60


class CollectError(Exception):
    """整份資料拿不到（跟「拿到了，剛好 0 個 session」是兩回事，畫面上不能長一樣）。"""


def default_paths(environ=os.environ, home=None):
    home = home or os.path.expanduser("~")
    claude = environ.get("CLAUDE_CONFIG_DIR") or os.path.join(home, ".claude")
    return {"home": home, "sessions": os.path.join(claude, "sessions"), "projects": os.path.join(claude, "projects"),
            "settings": os.path.join(claude, "settings.json"), "moshi": moshi.DEFAULT_DIR}


def _num(v):
    """欄位該是數字卻不是時當成 0。只用在「每個 session 各自的保護」之外的地方：那些地方一丟錯就是整頁看不到。"""
    try:
        return v if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else 0
    except OverflowError:  # JSON 允許任意長的整數，長到轉不成浮點數時 isfinite 自己會丟錯
        return 0


def pid_alive(pid):
    # 原生 Windows 上 os.kill(pid, 0) 不是「問它還在不在」：0 在那裡等於 Ctrl+C，失敗還會直接把程式結束掉
    if os.name == "nt":
        raise CollectError("不支援原生 Windows（請在 WSL 裡跑）")
    try:
        os.kill(int(pid), 0)
        return True
    except (ProcessLookupError, ValueError, TypeError, OverflowError):
        return False
    except PermissionError:
        return True


def read_procs(sessions_dir, alive=pid_alive):
    """回 (還活著的程式清單, 讀不懂的檔案數)。資料夾不存在＝丟 CollectError。"""
    if not os.path.isdir(sessions_dir):
        raise CollectError("找不到 " + sessions_dir + "：這台還沒跑過 Claude Code，或版本太舊（還不會記每個 session 的狀態）")
    try:
        os.listdir(sessions_dir)  # 沒有讀取權限時 glob 會安靜地回空的，看起來跟「真的沒有 session」一樣
    except OSError as e:
        raise CollectError("讀不了 " + sessions_dir + "（" + str(e) + "）")
    by_sid, skipped = {}, 0
    for f in glob.glob(os.path.join(sessions_dir, "[0-9]*.json")):
        try:
            with open(f, encoding="utf-8") as fh:
                p = json.load(fh)
            pid, sid = int(p.get("pid") or 0), p.get("sessionId")
        except Exception:  # 這裡在「每個 session 各自的保護」外面：任何怪檔都只能算一筆讀不懂，不能讓整輪失敗
            skipped += 1
            continue
        if not pid or not isinstance(sid, str) or not SID_RE.fullmatch(sid):
            skipped += 1
            continue
        if not alive(pid):
            continue
        # 同一個 session 被兩個程式開著（例如腳本用 `claude -p --continue` 接著你開著的那個）：
        # 留有人在用的那個；都是或都不是，才比誰最近有動靜。不然一支剛啟動的腳本會讓你自己那張卡不見
        if sid not in by_sid or _rank(p) > _rank(by_sid[sid]):
            by_sid[sid] = p
    return list(by_sid.values()), skipped


def _rank(proc):
    return (not is_headless(proc), _num(proc.get("updatedAt")))


def find_transcript(projects_dir, sid, known=None):
    """對話紀錄放在「開始時的資料夾」底下，中途 cd 走了也不會搬，所以用 sessionId 去找，不用現在的資料夾推。"""
    if known and os.path.exists(known):
        return known
    hits = glob.glob(os.path.join(glob.escape(projects_dir), "*", sid + ".jsonl"))
    return max(hits, key=os.path.getmtime) if hits else None


def project_of(cwd, home):
    if not cwd or not isinstance(cwd, str):
        return "", ""
    home, at_home = home.rstrip("/"), cwd.rstrip("/") == home.rstrip("/")
    short = "~" + cwd[len(home):] if at_home or cwd.startswith(home + "/") else cwd
    name = os.path.basename(cwd.rstrip("/")) or short
    if at_home:
        name = "~（家目錄）"
    return name, short


def _settings_say_1m(settings_path):
    try:
        with open(settings_path, encoding="utf-8") as fh:
            return "[1m]" in str(json.load(fh).get("model") or "").lower()
    except (OSError, ValueError, AttributeError):
        return False


def context_left(tokens, window_cfg, settings_path):
    """估「context 還剩幾 %」。對話紀錄裡看不出上限是 20 萬還是 100 萬，只能看設定檔的預設模型；
    用量已經超過 20 萬就一定是大的那種。估出來的數字畫面上會標「估計」。"""
    if not tokens:
        return None
    window = window_cfg
    if window == "auto":
        window = 1_000_000 if _settings_say_1m(settings_path) else 200_000
    if tokens > window:
        window = max(window, 1_000_000)
    return max(0, min(100, round(100 - tokens * 100 / window)))


def is_headless(proc):
    """沒有人坐在前面的 session：agent、SDK、`claude -p`（實測 entrypoint 都是 sdk-cli）。它們不會停下來等人，做完就直接結束——
    結束的那一刻檔案上寫的還是「正在忙」，所以不能拿「忙到一半不見了」當成當掉。
    只認已知的這一類（sdk 開頭）；欄位不見、是空的、或是沒看過的值，一律當成有人在用的 session：寧可多叫。"""
    return str(proc.get("entrypoint") or "").startswith("sdk")


def tracks_status(proc):
    """這個 session 該不該有 status。有人在用的一定有；沒有人坐在前面的那種在寫出第一個狀態之前可以安靜十幾分鐘，
    檔案裡連 updatedAt 都沒有——那是正常的，不是格式改了。"""
    return not is_headless(proc) or "statusUpdatedAt" in proc or "updatedAt" in proc


def state_of(proc, entry, helpers, ball_phrases, now, recent_write=False):
    """回 (狀態, 從什麼時候開始, 它在等你什麼)。認不得的 status 原樣帶出去，讓畫面放進急診室，不准安靜地當成「做完了」。"""
    status = proc.get("status")
    since = (proc.get("statusUpdatedAt") or proc.get("updatedAt") or proc.get("startedAt") or 0) / 1000
    if status is None and not tracks_status(proc):
        if recent_write:
            return "running", since, ""
        status = "idle"
    elif status is None and now - (proc.get("startedAt") or 0) / 1000 <= STARTUP_GRACE_SECONDS:
        status = "idle"
    if status == "busy":
        return "running", since, ""
    if status == "waiting":
        w = transcript.waiting_on(entry)
        if w and w["name"] in QUESTION_TOOLS:
            return "waiting_question", since, w["brief"] or ("計畫寫好了，等你看" if w["name"] == "ExitPlanMode" else "")
        if w:
            return "waiting_permission", since, "想用 " + w["name"] + ("：" + w["brief"] if w["brief"] else "")
        return "waiting_question", since, ""
    if status in IDLE_STATUSES:
        # 「球在你這裡」比「還有幫手在外面」優先：它已經停下來等你決定了，不能因為還有幫手沒回來就被放進「不用管它」
        if entry["lastOkAt"] and any(entry["lastReport"].startswith(p) for p in ball_phrases):
            return "ball", since, ""
        if helpers:
            return "helpers", since, ""
        return ("reported" if entry["lastOkAt"] else "idle"), since, ""
    return "unknown:" + ("沒有狀態" if status is None else str(status)[:40]), since, ""


def trouble_of(state, entry, now, last_write):
    """急診室：只回有證據的狀況，其他一律不算（寧可漏，不亂叫）。"""
    err_at = entry["lastErrAt"]
    if err_at and err_at > max(entry["lastOkAt"], entry["lastHumanAt"]) and not state.startswith("waiting"):
        return {"kind": "error", "text": "停在錯誤訊息：" + (entry["lastErrText"] or "不明錯誤"), "since": err_at}
    if state == "running" and last_write and now - last_write > STUCK_SECONDS:
        return {"kind": "stuck", "text": "顯示在跑，但已 " + str(int((now - last_write) // 60)) + " 分鐘沒有任何動靜", "since": last_write}
    return None


def _name_of(proc, entry):
    # 使用者自己取的名字最大；再來是 Claude Code 看對話自動取的標題；最後才是它從資料夾推的名字
    if proc.get("nameSource") == "user" and proc.get("name"):
        return str(proc["name"])[:60]
    return entry["title"] or str(proc.get("name") or "")[:60]


def build_row(proc, now, cfg, paths, panes, entry, tpath):
    sid = proc["sessionId"]
    helpers, sub_at = transcript.helpers_out(entry, tpath, now) if tpath else (0, 0)
    tmtime = 0
    if tpath:
        try:
            tmtime = os.path.getmtime(tpath)
        except OSError:
            tmtime = 0
    recent_write = bool(tmtime) and now - max(tmtime, sub_at) < RECENT_WRITE_SECONDS
    state, since, question = state_of(proc, entry, helpers, cfg["ballPhrases"], now, recent_write)
    name, short = project_of(proc.get("cwd"), paths["home"])
    pane = tmuxio.pane_of(proc.get("tmux"))
    tmux, window_name = "", ""
    if panes and pane in panes:  # 只給查得到的即時位置；查不到就留空＝不能點（寧可不能點，不要切錯視窗）
        tmux, window_name = panes[pane]
    else:
        pane = ""
    ctx = moshi.context_remaining(paths.get("moshi"), sid)
    estimated = ctx is None
    if estimated:
        ctx = context_left(entry["ctxTokens"], cfg["contextWindow"], paths["settings"])
    row = {
        "id": sid, "state": state, "since": since, "project": name, "path": short,
        "tmux": tmux, "pane": pane, "windowName": window_name, "name": _name_of(proc, entry),
        "helpers": helpers, "model": entry["model"], "context": ctx, "contextEstimated": estimated and ctx is not None,
        "lastUser": entry["lastUser"], "lastReport": entry["lastReport"], "question": question[:240],
        "turns": entry["turns"], "started": (proc.get("startedAt") or 0) / 1000,
        "lastActivity": max(tmtime, since, entry["lastHumanAt"], entry["lastOkAt"]),
    }
    if entry["lastCallAt"]:
        # 快取倒數：Claude 把對話內容暫存（1 小時或 5 分鐘），期間內繼續很便宜；過期後下一句要整段重讀
        row.update({"cacheExpiresAt": entry["lastCallAt"] + entry["ttl"], "ctxTokens": entry["ctxTokens"], "cacheTtl": entry["ttl"]})
    trouble = trouble_of(state, entry, now, max(tmtime, sub_at, since))
    if trouble:
        row["trouble"] = trouble
    return row


def _ended_rows(seen, live_ids, now):
    """上次還在、這次不見了的 session＝已關閉。回 (要顯示的列, 更新後的記憶)。"""
    rows, kept = [], {}
    for sid, m in seen.items():
        if sid in live_ids:
            kept[sid] = m
            continue
        if "endedAt" not in m:
            crashed = m.get("status") == "busy" and now - m.get("lastSeen", 0) <= CRASH_WATCH_SECONDS
            m = {**m, "endedAt": m.get("lastSeen", now), "crashed": crashed}
        if now - m["endedAt"] > KEEP_ENDED_SECONDS:
            continue
        kept[sid] = m
        row = {"id": sid, "state": "ended", "since": m["endedAt"], "project": m.get("project", ""), "path": m.get("path", ""),
               "tmux": "", "pane": "", "windowName": "", "name": m.get("name", ""), "helpers": 0}
        if m.get("crashed"):
            row["trouble"] = {"kind": "crashed", "text": "做到一半程式就停了（當掉，或視窗被直接關掉）", "since": m["endedAt"]}
        rows.append(row)
    return rows, kept


def _fallback_row(proc, now, paths, panes, exc):
    """這個 session 的細節整理失敗了，但程式還活著：用最基本的資訊出一張卡放進急診室。
    不能直接跳過——跳過的話下一步會以為它「不見了」，把一個活著的 session 畫成已關閉甚至當掉。"""
    name, short = project_of(proc.get("cwd"), paths["home"])
    pane = tmuxio.pane_of(proc.get("tmux"))
    tmux, window_name = panes[pane] if panes and pane in panes else ("", "")
    status = proc.get("status")
    state = {"busy": "running", "waiting": "waiting_question"}.get(status if isinstance(status, str) else None, "reported")
    since = (_num(proc.get("statusUpdatedAt")) or _num(proc.get("startedAt"))) / 1000  # 這張卡是最後一道防線，自己不能再丟錯
    return {"id": proc["sessionId"], "state": state, "since": since, "project": name, "path": short, "tmux": tmux,
            "pane": pane if tmux else "", "windowName": window_name, "name": str(proc.get("name") or "")[:60], "helpers": 0,
            "context": None, "contextEstimated": False, "lastUser": "", "lastReport": "", "question": "",
            "trouble": {"kind": "unreadable", "text": "這個 session 的細節讀不了（" + type(exc).__name__ + "），只知道它還開著", "since": now}}


def _last_resort_row(proc, now, exc):
    """連 _fallback_row 都失敗時的最小卡片：只有 id 和「讀不了」。有了它，單一程式檔不管長什麼樣都只影響自己那張卡。"""
    return {"id": proc["sessionId"], "state": "reported", "since": now, "project": "", "path": "", "tmux": "", "pane": "",
            "windowName": "", "name": "", "helpers": 0, "context": None, "contextEstimated": False, "lastUser": "", "lastReport": "",
            "question": "", "trouble": {"kind": "unreadable", "text": "這個 session 的資料完全讀不了（" + type(exc).__name__ + "），只知道它還開著", "since": now}}


def _usable_state(state):
    """存檔可能被改壞或是別的版本寫的：形狀不對就整份重來，不要每一輪都失敗。"""
    return (isinstance(state, dict) and state.get("v") == STATE_VERSION
            and all(isinstance(state.get(k), dict) for k in ("transcripts", "tpaths", "seen"))
            and all(isinstance(m, dict) for m in state["seen"].values()))


def _warnings(paths, rows, found, bad_lines):
    """上游壞掉但畫面看起來正常的情況，要在最上面講出來。"""
    out = []
    live = len(rows)
    if not os.path.isdir(paths["projects"]):
        out.append("找不到對話紀錄資料夾（" + paths["projects"] + "）：只看得到誰開著，看不到回報、幫手、快取倒數")
    elif live >= 2 and found == 0:
        out.append("開著的 " + str(live) + " 個 session 全都找不到對話紀錄，Claude Code 可能改了存放位置")
    if bad_lines:
        out.append("對話紀錄有 " + str(bad_lines) + " 行看不懂，Claude Code 可能改了格式，狀態可能不準")
    return out


def collect(now, cfg, paths, state=None, alive=pid_alive, list_panes=None):
    """整理一輪。回 (給畫面的資料, 要存起來的記憶)。state 是上一輪回的那份記憶（第一次給 None）。"""
    if not _usable_state(state):
        state = {"v": STATE_VERSION, "transcripts": {}, "tpaths": {}, "seen": {}}
    procs, skipped = read_procs(paths["sessions"], alive)
    try:
        panes = list_panes() if list_panes else None
    except Exception:  # tmux 那邊出任何怪事都只是「不知道位置」，卡片點不過去而已
        panes = None
    rows, transcripts, tpaths, seen = [], {}, {}, dict(state["seen"])
    found = bad_lines = 0
    for proc in procs:
        sid, tpath, entry, headless = proc["sessionId"], None, None, False
        try:
            headless = is_headless(proc)
            # startedAt 不是數字時當成 0＝很久以前，往下走，由 build_row 把它變成急診室的卡
            if headless and now - _num(proc.get("startedAt")) / 1000 < HEADLESS_MIN_AGE_SECONDS:
                continue
            tpath = find_transcript(paths["projects"], sid, state["tpaths"].get(sid))
            entry = transcript.update(state["transcripts"].get(tpath), tpath, now) if tpath else transcript.new_entry()
            row = build_row(proc, now, cfg, paths, panes, entry, tpath)
        except Exception as exc:  # 一個 session 的資料怪掉不影響其他人；它自己進急診室，不是安靜地消失
            try:
                row = _fallback_row(proc, now, paths, panes, exc)
            except Exception as exc2:
                row = _last_resort_row(proc, now, exc2)
        if tpath and entry is not None:
            transcripts[tpath], tpaths[sid] = entry, tpath
            found += 1
            bad_lines += transcript.suspicious_lines(entry)
        if headless:
            row["headless"] = True
        rows.append(row)
        # 沒有人坐在前面的不記進「最近關掉的」：它們跑完就走是常態，記了只會把「已關閉」灌滿、還會被誤判成當掉
        if headless:
            seen.pop(sid, None)
        else:
            seen[sid] = {"name": row["name"], "project": row["project"], "path": row["path"], "status": proc.get("status"), "lastSeen": now}
    ended, seen = _ended_rows(seen, {r["id"] for r in rows}, now)
    payload = {"generatedAt": now, "sessions": rows + ended, "skipped": skipped,
               "warnings": _warnings(paths, rows, found, bad_lines),
               "sources": {"tmux": panes is not None, "moshi": moshi.available(paths.get("moshi")),
                           "transcripts": {"found": found, "missing": len(rows) - found}}}
    return payload, {"v": STATE_VERSION, "transcripts": transcripts, "tpaths": tpaths, "seen": seen}
