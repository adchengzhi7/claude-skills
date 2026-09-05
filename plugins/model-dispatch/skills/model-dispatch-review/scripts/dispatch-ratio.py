#!/usr/bin/env python3
"""
模型派工對帳：萬用 agent（general-purpose / claude / 未指定 / Explore / Plan）派工時
「有沒有明確帶 model」的比例，以及各 agent 實際跑的模型分布。

這是週回顧的核心指標——它抓的是「主 Claude 有沒有照派工表做」，
agent-usage-report 只算次數、看不到這個。

用法:
    python3 dispatch-ratio.py            # 近 7 天
    python3 dispatch-ratio.py --days 30
    python3 dispatch-ratio.py --json
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECTS_DIR = Path.home() / ".claude" / "projects"
CATCH_ALL = {"general-purpose", "claude", "", "Explore", "Plan"}
INHERIT_BY_DESIGN = {"fork"}


def parse_ts(ts):
    if not ts:
        return None
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def collect(since):
    rows = []
    if not PROJECTS_DIR.exists():
        return rows
    for f in PROJECTS_DIR.glob("*/*.jsonl"):
        try:
            if datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc) < since:
                continue
            with f.open("r", encoding="utf-8") as fh:
                for line in fh:
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if d.get("type") != "assistant":
                        continue
                    ts = parse_ts(d.get("timestamp"))
                    if not ts or ts < since:
                        continue
                    msg = d.get("message") or {}
                    for c in msg.get("content") or []:
                        if not isinstance(c, dict) or c.get("type") != "tool_use":
                            continue
                        if c.get("name") not in ("Agent", "Task"):
                            continue
                        inp = c.get("input") or {}
                        if not isinstance(inp, dict):
                            continue
                        rows.append({
                            "agent": (inp.get("subagent_type") or "").strip(),
                            "model": (inp.get("model") or "").strip(),
                            "session": d.get("sessionId", ""),
                            "ts": ts.isoformat(),
                        })
        except OSError:
            continue
    return rows


def summarize(rows):
    by_agent = defaultdict(lambda: {"total": 0, "explicit": 0, "models": Counter()})
    for r in rows:
        a = r["agent"] or "(未指定)"
        s = by_agent[a]
        s["total"] += 1
        if r["model"]:
            s["explicit"] += 1
            s["models"][r["model"]] += 1
        else:
            s["models"]["(繼承主 session)" if (r["agent"] in CATCH_ALL) else "(frontmatter 綁定)"] += 1
    core_total = sum(s["total"] for a, s in by_agent.items() if (a if a != "(未指定)" else "") in CATCH_ALL)
    core_explicit = sum(s["explicit"] for a, s in by_agent.items() if (a if a != "(未指定)" else "") in CATCH_ALL)
    return by_agent, core_total, core_explicit


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--json", action="store_true")
    a = p.parse_args()
    since = datetime.now(timezone.utc) - timedelta(days=a.days)
    rows = collect(since)
    by_agent, core_total, core_explicit = summarize(rows)
    sessions = len({r["session"] for r in rows if r["session"]})

    if a.json:
        out = {
            "days": a.days, "dispatches": len(rows), "sessions": sessions,
            "catch_all_total": core_total, "catch_all_explicit": core_explicit,
            "by_agent": {k: {"total": v["total"], "explicit": v["explicit"], "models": dict(v["models"])}
                         for k, v in by_agent.items()},
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    pct = (100 * core_explicit / core_total) if core_total else 0
    print(f"# 模型派工對帳（近 {a.days} 天）\n")
    print(f"派工 {len(rows)} 次 / {sessions} 個 session")
    print(f"**核心指標：萬用 agent 明確帶 model 的比例 = {core_explicit}/{core_total} = {pct:.0f}%**")
    print("（萬用 agent = general-purpose / claude / 未指定 / Explore / Plan；具名專才已綁模型不計）\n")
    print("| agent | 派工 | 帶 model | 比例 | 實際模型分布 |")
    print("|---|---|---|---|---|")
    for agent, s in sorted(by_agent.items(), key=lambda kv: -kv[1]["total"]):
        key = "" if agent == "(未指定)" else agent
        tag = "" if key in CATCH_ALL else "（專才/綁定）"
        ratio = f"{100 * s['explicit'] / s['total']:.0f}%" if key in CATCH_ALL else "-"
        dist = ", ".join(f"{m} {n}" for m, n in s["models"].most_common())
        print(f"| `{agent}`{tag} | {s['total']} | {s['explicit']} | {ratio} | {dist} |")
    print()
    print("讀法：比例掉了＝主 Claude 沒照派工表做，是執行紀律問題；"
          "某個專才 agent 連續被打回＝該升級；機械活長期零失誤＝可降級試。一次只動一個設定。")


if __name__ == "__main__":
    main()
