"""測試共用：在暫存資料夾裡擺一個假的 ~/.claude，寫假的程式清單與對話紀錄。"""
import datetime
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from office import config  # noqa: E402

NOW = 1_800_000_000.0
SID = "test-session-aaaa"


def iso(ts):
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).isoformat().replace("+00:00", "Z")


class FakeHome:
    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.paths = {"home": self.root, "sessions": os.path.join(self.root, ".claude", "sessions"),
                      "projects": os.path.join(self.root, ".claude", "projects"),
                      "settings": os.path.join(self.root, ".claude", "settings.json"),
                      "moshi": os.path.join(self.root, "moshi")}
        os.makedirs(self.paths["sessions"])
        os.makedirs(self.paths["projects"])

    def cleanup(self):
        self._tmp.cleanup()

    def proc(self, pid, sid=SID, status="idle", **extra):
        p = {"pid": pid, "sessionId": sid, "cwd": os.path.join(self.root, "Projects", "shop"), "startedAt": (NOW - 3600) * 1000,
             "kind": "interactive", "entrypoint": "cli", "status": status, "statusUpdatedAt": (NOW - 60) * 1000, "updatedAt": (NOW - 60) * 1000,
             "tmux": "work:@1.%5", "name": "shop", "nameSource": "derived", **extra}
        with open(os.path.join(self.paths["sessions"], str(pid) + ".json"), "w", encoding="utf-8") as fh:
            json.dump(p, fh)
        return p

    def transcript(self, lines, sid=SID, folder="-somewhere-else", append=False):
        d = os.path.join(self.paths["projects"], folder)
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, sid + ".jsonl")
        with open(path, "a" if append else "w", encoding="utf-8") as fh:
            for o in lines:
                fh.write((o if isinstance(o, str) else json.dumps(o, ensure_ascii=False, separators=(",", ":"))) + "\n")
        return path


def cfg(**over):
    return {**config.DEFAULTS, **over}


def human(text, ts):
    return {"type": "user", "timestamp": iso(ts), "origin": {"kind": "human"}, "message": {"role": "user", "content": text}}


def assistant(ts, text=None, tool=None, usage=None, model="claude-test", **extra):
    content = []
    if text:
        content.append({"type": "text", "text": text})
    if tool:
        content.append({"type": "tool_use", "id": tool[0], "name": tool[1], "input": tool[2]})
    msg = {"role": "assistant", "model": model, "content": content}
    if usage:
        msg["usage"] = usage
    return {"type": "assistant", "timestamp": iso(ts), "message": msg, **extra}


def tool_result(tool_id, ts, result=None, text="ok"):
    o = {"type": "user", "timestamp": iso(ts),
         "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_id, "content": text}]}}
    if result is not None:
        o["toolUseResult"] = result
    return o
