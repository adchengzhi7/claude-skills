#!/usr/bin/env python3
"""
Agent / Skill 使用狀況報告。

掃描 ~/.claude/projects/*/*.jsonl 取得 Task tool 觸發紀錄，
產出 Markdown 報告。

用法:
    python3 report.py                  # 近 7 天
    python3 report.py --days 30        # 近 30 天
    python3 report.py --since 2026-04-01
    python3 report.py --json           # JSON 輸出
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from glob import glob
from pathlib import Path

PROJECTS_DIR = Path.home() / ".claude" / "projects"

# 想單獨追蹤的 agent（逗號分隔），例：AGENT_USAGE_TRACKED=debugger,feature-builder
# 沒設就不出這一段。
TRACKED_AGENTS = [a.strip() for a in os.environ.get("AGENT_USAGE_TRACKED", "").split(",") if a.strip()]


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=7,
                   help="統計近 N 天（預設 7）")
    p.add_argument("--since", type=str,
                   help="從指定日期統計（YYYY-MM-DD）")
    p.add_argument("--json", action="store_true",
                   help="輸出 JSON 而非 Markdown")
    return p.parse_args()


def parse_timestamp(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def cwd_to_project(cwd: str) -> str:
    """把 cwd 路徑簡化成可讀的專案名稱。"""
    if not cwd:
        return "unknown"
    p = Path(cwd)
    parts = p.parts
    # .../Projects/<group>/<name> → <name>
    if "Projects" in parts:
        idx = parts.index("Projects")
        if idx + 2 < len(parts):
            return parts[idx + 2]
        if idx + 1 < len(parts):
            return parts[idx + 1]
    # 一般情況用最後兩段
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    return p.name or cwd


def collect(since: datetime) -> dict:
    """掃描 transcript 收集 agent 觸發記錄。"""
    if not PROJECTS_DIR.exists():
        return {"records": [], "scanned_files": 0}

    records = []
    scanned = 0
    files = list(PROJECTS_DIR.glob("*/*.jsonl"))

    for fpath in files:
        # 檔案 mtime 早於 since 就跳過（小優化）
        try:
            if datetime.fromtimestamp(fpath.stat().st_mtime, tz=timezone.utc) < since:
                continue
        except OSError:
            continue

        scanned += 1
        try:
            with fpath.open("r", encoding="utf-8") as f:
                for line in f:
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if d.get("type") != "assistant":
                        continue

                    ts = parse_timestamp(d.get("timestamp"))
                    if not ts or ts < since:
                        continue

                    cwd = d.get("cwd", "")
                    project = cwd_to_project(cwd)
                    branch = d.get("gitBranch") or ""
                    session = d.get("sessionId", "")
                    is_sidechain = d.get("isSidechain", False)

                    msg = d.get("message", {})
                    content = msg.get("content", []) if isinstance(msg, dict) else []
                    if not isinstance(content, list):
                        continue

                    for c in content:
                        if not isinstance(c, dict):
                            continue
                        if c.get("type") != "tool_use":
                            continue
                        inp = c.get("input", {})
                        if not isinstance(inp, dict):
                            continue
                        sa = inp.get("subagent_type")
                        if not sa:
                            continue
                        records.append({
                            "agent": sa,
                            "cwd": cwd,
                            "project": project,
                            "branch": branch,
                            "timestamp": ts.isoformat(),
                            "session": session,
                            "description": inp.get("description", "")[:120],
                            "is_sidechain": is_sidechain,
                            "file": fpath.name,
                        })
        except OSError:
            continue

    return {"records": records, "scanned_files": scanned}


def list_known_agents(cwds: set[str]) -> dict[str, str]:
    """讀取已定義的 agent 清單：global + 範圍內 transcript 出現過的每個專案目錄。"""
    known = {}
    g = Path.home() / ".claude" / "agents"
    if g.exists():
        for f in g.glob("*.md"):
            known[f.stem] = "global"
    for cwd in sorted(c for c in cwds if c):
        agents_dir = Path(cwd) / ".claude" / "agents"
        if agents_dir.is_dir():
            for f in agents_dir.glob("*.md"):
                if f.stem not in known:
                    known[f.stem] = f"project:{Path(cwd).name}"
    return known


def build_markdown(data: dict, since: datetime, days: int) -> str:
    records = data["records"]
    scanned = data["scanned_files"]
    now = datetime.now(timezone.utc)
    end_str = now.strftime("%Y-%m-%d %H:%M")
    start_str = since.strftime("%Y-%m-%d %H:%M")

    by_agent = Counter(r["agent"] for r in records)
    by_project_agent = defaultdict(Counter)
    for r in records:
        by_project_agent[r["project"]][r["agent"]] += 1

    last_seen = {}
    for r in records:
        ts = parse_timestamp(r["timestamp"])
        if not ts:
            continue
        if r["agent"] not in last_seen or last_seen[r["agent"]] < ts:
            last_seen[r["agent"]] = ts

    sessions = {r["session"] for r in records if r["session"]}

    lines = []
    lines.append(f"# Agent 使用狀況報告")
    lines.append("")
    lines.append(f"範圍：{start_str} → {end_str}（近 {days} 天）")
    lines.append(f"掃描 transcript：{scanned} 個檔案")
    lines.append(f"總 agent 觸發：**{len(records)}** 次")
    lines.append(f"活躍 session：{len(sessions)} 個")
    lines.append("")

    # 指定追蹤的 agents（可選）
    if TRACKED_AGENTS:
        lines.append("## 指定追蹤的 agent")
        lines.append("")
        lines.append("| Agent | 觸發次數 | 最後使用 | 健康度 |")
        lines.append("|---|---|---|---|")
    for name in TRACKED_AGENTS:
        count = by_agent.get(name, 0)
        last = last_seen.get(name)
        last_str = last.strftime("%Y-%m-%d %H:%M") if last else "—"
        if count >= 3:
            health = "OK 健康"
        elif count >= 1:
            health = "輕度使用"
        else:
            health = "未觸發"
        lines.append(f"| `{name}` | {count} | {last_str} | {health} |")
    lines.append("")

    # 全部 agent 排行
    lines.append("## 全部 agent 觸發排行")
    lines.append("")
    if not by_agent:
        lines.append("（範圍內無紀錄）")
    else:
        lines.append("| Agent | 次數 | 最後使用 |")
        lines.append("|---|---|---|")
        for agent, count in by_agent.most_common():
            last = last_seen.get(agent)
            last_str = last.strftime("%Y-%m-%d %H:%M") if last else "—"
            lines.append(f"| `{agent}` | {count} | {last_str} |")
    lines.append("")

    # 按專案分布
    lines.append("## 按專案分布")
    lines.append("")
    if not by_project_agent:
        lines.append("（無資料）")
    else:
        for project in sorted(by_project_agent.keys()):
            agents = by_project_agent[project]
            total = sum(agents.values())
            lines.append(f"### {project}（{total} 次）")
            for agent, count in agents.most_common():
                lines.append(f"- `{agent}`：{count}")
            lines.append("")

    # Kill switch 候選
    known = list_known_agents({r.get("cwd", "") for r in records})
    used_agents = set(by_agent.keys())
    silent = sorted(name for name in known if name not in used_agents)
    lines.append("## Kill Switch 候選（範圍內 0 次觸發）")
    lines.append("")
    if not silent:
        lines.append("（無）")
    else:
        for name in silent:
            scope = known[name]
            lines.append(f"- `{name}`（{scope}）")
        lines.append("")
        lines.append(f"**判斷規則**：30 天 0 次 → 建議檢討；7 天 0 次但有歷史 → 觀察")
    lines.append("")

    # 最近觸發樣本
    lines.append("## 最近 10 次觸發（樣本）")
    lines.append("")
    recent = sorted(records, key=lambda r: r["timestamp"], reverse=True)[:10]
    if not recent:
        lines.append("（無資料）")
    else:
        for r in recent:
            ts = parse_timestamp(r["timestamp"])
            ts_str = ts.strftime("%m-%d %H:%M") if ts else "?"
            sidechain = "(子)" if r["is_sidechain"] else ""
            desc = r["description"] or "(無描述)"
            lines.append(f"- {ts_str} `{r['agent']}` @ {r['project']} {sidechain}")
            lines.append(f"  > {desc}")
    lines.append("")

    return "\n".join(lines)


def main():
    args = parse_args()
    if args.since:
        try:
            since = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            print(f"無效日期格式（要 YYYY-MM-DD）: {args.since}", file=sys.stderr)
            sys.exit(1)
        days = (datetime.now(timezone.utc) - since).days
    else:
        days = args.days
        since = datetime.now(timezone.utc) - timedelta(days=days)

    data = collect(since)

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    print(build_markdown(data, since, days))


if __name__ == "__main__":
    main()
