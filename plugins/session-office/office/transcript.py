"""增量讀 Claude Code 的對話紀錄檔（~/.claude/projects/<資料夾>/<sessionId>.jsonl）。

每次只讀上次之後新增的部分，把辦公室需要的事記進一份小摘要（entry）：
最後一句人打的話、最後一句回報、還沒回答的工具呼叫（＝在等你什麼）、派出去還沒回來的 agent、快取倒數、錯誤訊息、標題。
"""
import datetime
import json
import os
import re

VERSION = 1
# 第一次讀一份很大的紀錄檔時只看最後這麼多：再早的內容對「現在的狀態」沒有影響，從頭讀會讓第一次開頁面卡很久
FIRST_READ_TAIL = 8 * 1024 * 1024
# 超過這麼長的單行（多半是工具回傳的整份檔案）不解析，只用字串比對找「哪個工具呼叫有回應了」
BIG_LINE = 200_000
DEFAULT_CACHE_TTL = 3600
# 派出去超過 6 小時沒回來的不算（多半是 session 重開後通知遺失）
HELPER_STALE_SECONDS = 6 * 3600
# agent 自己的工作紀錄這段時間內有寫入＝一定還在工作（不管通知怎麼記）
SUB_ACTIVE_SECONDS = 120
# 看不懂的行要「夠多、而且佔比夠高」才提醒：開很久的 session 零星累積幾行怪資料不值得一直叫，
# 格式整個改掉時新的行幾乎全都看不懂，兩個門檻很快都會過
BAD_LINES_WARN = 10
BAD_LINES_RATIO = 0.05
MAX_PENDING = 50
MAX_AGENTS = 300
DONE_RES = (re.compile(r"<task-id>([a-z0-9]+)</task-id>"), re.compile(r'<agent-message from=\\?"([a-z0-9]+)'))
TOOL_RESULT_ID = re.compile(r'"tool_use_id"\s*:\s*"([^"]+)"')
COMMAND_NAME = re.compile(r"<command-name>\s*(/[^<\s]+)")


def new_entry():
    return {"v": VERSION, "offset": 0, "agents": {}, "pending": {}, "lastCallAt": 0, "ctxTokens": 0, "ttl": DEFAULT_CACHE_TTL,
            "lastHumanAt": 0, "lastUser": "", "turns": 0, "lastOkAt": 0, "lastReport": "", "lastErrAt": 0, "lastErrText": "",
            "title": "", "model": "", "badLines": 0, "lines": 0}


def _ts(o, fallback):
    try:
        return datetime.datetime.fromisoformat(o["timestamp"].replace("Z", "+00:00")).timestamp()
    except (KeyError, ValueError, AttributeError, TypeError):
        return fallback


def _text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(p.get("text") or "" for p in content if isinstance(p, dict) and p.get("type") == "text")
    return ""


def _brief(name, inp):
    """等你授權時，卡片上要寫「它想做什麼」。只拿最能說明的那一個欄位。"""
    if not isinstance(inp, dict):
        return ""
    if name == "AskUserQuestion":
        qs = inp.get("questions") or []
        return str(qs[0].get("question") or "") if qs and isinstance(qs[0], dict) else ""
    for key in ("command", "file_path", "url", "description", "prompt", "skill", "query"):
        if isinstance(inp.get(key), str) and inp[key].strip():
            return inp[key].strip()
    return ""


def _is_human(o, content):
    if o.get("isCompactSummary"):  # 自動壓縮產生的摘要長得像一句使用者的話，但不是人打的
        return False
    origin = o.get("origin")
    if isinstance(origin, dict):
        return origin.get("kind") == "human"
    # 沒有 origin 欄位的也很常見（現行版本一樣會有，不是只有舊版）——這條不是死碼，別刪：
    # 純文字、不是工具回傳、不是系統塞的（那些都用 < 開頭）才當成人打的
    return isinstance(content, str) and "toolUseResult" not in o and not o.get("isMeta") and not content.lstrip().startswith("<")


def _message(o):
    msg = o.get("message")
    return msg if isinstance(msg, dict) else {}


def _apply_user(entry, o, ts):
    content = _message(o).get("content")
    if _is_human(o, content) and ts >= entry["lastHumanAt"]:
        text = _text_of(content).strip()
        entry["lastHumanAt"] = ts
        entry["turns"] += 1
        entry["pending"] = {}  # 人又說話了＝之前卡著的工具呼叫都不算數了
        cmd = COMMAND_NAME.search(text)
        if cmd:
            entry["lastUser"] = cmd.group(1)
        elif text and not text.startswith("<"):
            entry["lastUser"] = text[:200]
    r = o.get("toolUseResult")
    if isinstance(r, dict) and r.get("status") == "async_launched":
        hid = r.get("agentId") or r.get("taskId")
        if hid:
            a = entry["agents"].setdefault(str(hid), {"out": 0, "back": 0})
            a["out"] = max(a["out"], ts)
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") == "tool_result":
                entry["pending"].pop(part.get("tool_use_id"), None)


def _apply_assistant(entry, o, ts):
    msg = _message(o)
    content = msg.get("content")
    parts = [p for p in (content if isinstance(content, list) else []) if isinstance(p, dict)]
    if o.get("isApiErrorMessage"):
        # 連線／額度／登入錯誤：Claude Code 自己寫一句假回覆（usage 全是 0）。不能當成一次真回覆，否則快取倒數會被重設
        if ts >= entry["lastErrAt"]:
            entry["lastErrAt"] = ts
            text = " ".join(p.get("text") or "" for p in parts).strip()
            entry["lastErrText"] = (text or str(o.get("error") or "不明錯誤"))[:160]
        return
    if msg.get("model") and msg.get("model") != "<synthetic>":
        if ts >= entry["lastOkAt"]:
            entry["lastOkAt"] = ts
        entry["model"] = msg["model"]
    for part in parts:
        if part.get("type") == "text" and (part.get("text") or "").strip():
            entry["lastReport"] = part["text"].strip()[:240]
        elif part.get("type") == "tool_use" and part.get("id"):
            name, inp = part.get("name") or "", part.get("input")
            entry["pending"][part["id"]] = {"name": name, "brief": _brief(name, inp)[:240]}
            to = inp.get("to") if isinstance(inp, dict) else None
            if name == "SendMessage" and to in entry["agents"]:  # 叫一個派過的 agent 回去續做＝又派出去了
                entry["agents"][to]["out"] = max(entry["agents"][to]["out"], ts)
    u = msg.get("usage")
    if isinstance(u, dict) and u and ts >= entry["lastCallAt"]:
        entry["lastCallAt"] = ts
        entry["ctxTokens"] = (u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0)
        cc = u.get("cache_creation") if isinstance(u.get("cache_creation"), dict) else {}
        if cc.get("ephemeral_5m_input_tokens") and not cc.get("ephemeral_1h_input_tokens"):
            entry["ttl"] = 300
        elif cc.get("ephemeral_1h_input_tokens"):
            entry["ttl"] = 3600


def _apply_line(entry, line, now):
    if len(line) > BIG_LINE:
        for tid in TOOL_RESULT_ID.findall(line):
            entry["pending"].pop(tid, None)
        return
    try:
        o = json.loads(line)
    except ValueError:
        return
    if not isinstance(o, dict) or o.get("isSidechain"):
        return
    kind, ts = o.get("type"), _ts(o, now)
    if kind == "ai-title" and isinstance(o.get("aiTitle"), str):
        entry["title"] = o["aiTitle"].strip()[:60]
    elif kind == "user":
        _apply_user(entry, o, ts)
    elif kind == "assistant":
        _apply_assistant(entry, o, ts)
    # 完成通知：佇列的「移除」那一行時間晚、內容是舊通知，會把還在外面的 agent 誤判成回來了，所以只認 enqueue
    if kind == "queue-operation" and o.get("operation") != "enqueue":
        return
    if "<task-id>" in line or "agent-message from=" in line:
        for rx in DONE_RES:
            for hid in rx.findall(line):
                a = entry["agents"].setdefault(hid, {"out": 0, "back": 0})
                a["back"] = max(a["back"], ts)


def update(entry, path, now):
    """讀 path 上次之後新增的部分，回新的 entry（不改傳進來的那份）。檔案讀不到就原樣回。"""
    if not _usable(entry):
        entry = new_entry()
    entry = {**new_entry(), **entry, "agents": {k: dict(v) for k, v in entry["agents"].items()}, "pending": dict(entry["pending"])}
    try:
        size = os.path.getsize(path)
        if size < entry["offset"]:  # 檔案變小＝被換掉了，從頭來
            entry = new_entry()
        if size == entry["offset"]:
            return entry
        with open(path, "rb") as fh:
            if entry["offset"] == 0 and size > FIRST_READ_TAIL:
                fh.seek(size - FIRST_READ_TAIL)
                fh.readline()  # 丟掉切到一半的那一行
                entry["offset"] = fh.tell()
            fh.seek(entry["offset"])
            chunk = fh.read()
    except OSError:  # 剛好被刪、權限不對：這一輪先不讀，下一輪再試
        return entry
    cut = chunk.rfind(b"\n") + 1  # 只處理完整的行，寫到一半的留到下次
    entry["offset"] += cut
    for raw in chunk[:cut].splitlines():
        entry["lines"] += 1
        try:
            _apply_line(entry, raw.decode("utf-8", "ignore"), now)
        except Exception:  # 一行長得跟預期不同只跳過那一行並記一筆；不能讓它把整個 session 拖成「讀不到」
            entry["badLines"] += 1
    if len(entry["pending"]) > MAX_PENDING:
        entry["pending"] = dict(list(entry["pending"].items())[-MAX_PENDING:])
    if len(entry["agents"]) > MAX_AGENTS:
        keep = sorted(entry["agents"].items(), key=lambda kv: max(kv[1]["out"], kv[1]["back"]))[-MAX_AGENTS:]
        entry["agents"] = dict(keep)
    return entry


def _usable(entry):
    """存檔裡的摘要可能被改壞或是舊格式：形狀不對就整份重來，不要每一輪都在同一個地方跌倒。"""
    return (isinstance(entry, dict) and entry.get("v") == VERSION and isinstance(entry.get("agents"), dict)
            and isinstance(entry.get("pending"), dict) and isinstance(entry.get("offset"), int)
            and all(isinstance(a, dict) and "out" in a and "back" in a for a in entry["agents"].values()))


def suspicious_lines(entry):
    """這個 session 看不懂的行數——只有夠多、佔比也夠高時才回報，否則回 0。"""
    bad, total = entry.get("badLines", 0), max(entry.get("lines", 0), 1)
    return bad if bad >= BAD_LINES_WARN and bad / total >= BAD_LINES_RATIO else 0


def sub_write_at(path):
    """這個 session 派出去的 agent 最後一次寫紀錄的時間，以及 2 分鐘內還在寫的有哪幾個。"""
    sub_dir = path[:-6] + "/subagents" if path.endswith(".jsonl") else ""
    latest, files = 0, []
    if sub_dir and os.path.isdir(sub_dir):
        for root, _dirs, names in os.walk(sub_dir):
            for fn in names:
                if fn.endswith(".jsonl"):
                    try:
                        files.append((os.path.getmtime(os.path.join(root, fn)), fn))
                    except OSError:
                        pass
    if files:
        latest = max(m for m, _ in files)
    return latest, files


def helpers_out(entry, path, now):
    """派出去還沒回來的 agent 有幾個。每個 agent 比「最後一次派出去」和「最後一次回來」的時間，派出去比較晚＝還在外面。"""
    pending = {k for k, a in entry["agents"].items() if a["out"] > a["back"] and now - a["out"] < HELPER_STALE_SECONDS}
    latest, files = sub_write_at(path)
    for mtime, fn in files:
        if now - mtime < SUB_ACTIVE_SECONDS:
            # 檔名可能是 agent-<id>.jsonl 或 agent-<id>-<名字>.jsonl：都取 id，才不會跟通知算出來的那一個重複算
            m = re.match(r"agent-([a-z0-9]+)", fn)
            pending.add(m.group(1) if m else fn)
    return len(pending), latest


def waiting_on(entry):
    """還沒有回應的最後一個工具呼叫（＝session 停下來在等的那件事）。沒有就回 None。"""
    if not entry["pending"]:
        return None
    return list(entry["pending"].values())[-1]
