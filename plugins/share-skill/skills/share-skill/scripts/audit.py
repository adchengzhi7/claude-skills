"""PII / share-readiness auditor。

用法：
    audit.py <skill-path>            # 全 skill 審查
    audit.py --staged-only           # 只審查 git staged 檔案（給 pre-commit hook 用）

退出碼：
    0 = 過關（可能有 WARN）
    1 = 有 BLOCK 級別 PII，必修

設計：grep 規則 + allowlist。寧願誤判要修，也不能漏。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable, NamedTuple

# 預設 allowlist 路徑（相對於本檔）
DEFAULT_ALLOWLIST = Path(__file__).resolve().parent.parent / "allowlist.json"

# 排除的目錄 / 副檔名
EXCLUDE_DIRS = {".git", "__pycache__", "node_modules", ".venv", ".DS_Store", "build", "dist"}
EXCLUDE_BINARY_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic", ".mov", ".mp4", ".zip", ".tar", ".gz"}


class Finding(NamedTuple):
    severity: str        # BLOCK / WARN / INFO
    rule: str            # 規則名稱
    file: str            # 相對路徑
    line: int            # 行號
    text: str            # 命中的行文字
    suggestion: str      # 修法建議


# PII 規則
RULES = [
    # name, severity, regex pattern, suggestion
    ("email_personal", "BLOCK",
     r"\b[A-Za-z0-9._%+-]+@(?!example\.com|gmail\.com\b\s*as|test\.com)[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
     "用 your@email.com / you@example.com"),
    ("tax_id_8digit", "BLOCK",
     r"\b(?<![\d])\d{8}(?![\d])\b",
     "改 12345678 (placeholder)"),
    ("tw_plate", "BLOCK",
     r"\b[A-Z]{2,3}-\d{4}\b|\b[A-Z]{3}\d{4}\b|\b\d{4}-[A-Z]{2,3}\b",
     "改 ABC1234"),
    ("driver_license", "BLOCK",
     r"\b[A-Z]{2}\d{6}\b",
     "改 NA000001"),
    ("uuid_v4", "BLOCK",
     r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
     "改 00000000-0000-0000-0000-000000000000"),
    ("invoice_no_stripe", "BLOCK",
     r"\b[A-Z]{2,8}-\d{4,5}\b|\b#\d{4}-\d{4}(?:-\d{4})?\b",
     "改 XXXXXX-NNNNN"),
    ("credit_card_last4", "BLOCK",
     r"••••\d{4}\b|\b\*{4,}\d{4}\b",
     "改 ••••0000"),
    ("absolute_user_path", "WARN",
     r"/Users/[a-z0-9_-]+/",
     "用 ~/  或 $HOME/"),
    ("hardcoded_password_like", "BLOCK",
     r"(?i)(password|passwd|secret|api[_-]?key|token)\s*=\s*['\"][^'\"]{8,}['\"]",
     "用 環境變數 / Keychain / config 不寫死"),
]

# 必要文件
REQUIRED_FILES = ["LICENSE", "DISCLAIMER.md", "README.md", "SKILL.md"]


def load_allowlist(path: Path = DEFAULT_ALLOWLIST) -> set[str]:
    """讀 allowlist — 命中後降為 INFO。"""
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    out: set[str] = set()
    for v in data.values():
        if isinstance(v, list):
            out.update(str(x) for x in v)
    return out


def iter_files(root: Path) -> Iterable[Path]:
    if root.is_file():
        if root.suffix.lower() not in EXCLUDE_BINARY_EXT:
            yield root
        return
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in EXCLUDE_DIRS for part in p.parts):
            continue
        if p.suffix.lower() in EXCLUDE_BINARY_EXT:
            continue
        yield p


def scan_text(text: str, file_rel: str, allowlist: set[str]) -> list[Finding]:
    findings: list[Finding] = []
    for line_no, line in enumerate(text.splitlines(), 1):
        for rule_name, severity, pattern, suggestion in RULES:
            for m in re.finditer(pattern, line):
                hit = m.group(0)
                if any(allowed in hit for allowed in allowlist):
                    continue
                # 過濾明顯 placeholder
                if rule_name == "tax_id_8digit" and hit in ("12345678", "00000000"):
                    continue
                if rule_name == "tw_plate" and hit in ("ABC1234", "ABC-1234"):
                    continue
                if rule_name == "email_personal" and any(
                    placeholder in hit.lower() for placeholder in
                    ("@example.com", "your@", "you@", "personal@example",
                     "dev@example", "@yourdomain", "@localhost", "@test")
                ):
                    continue
                if rule_name == "uuid_v4" and hit == "00000000-0000-0000-0000-000000000000":
                    continue
                if rule_name == "invoice_no_stripe" and hit in ("XXXXXX-NNNNN", "#XXXX-YYYY"):
                    continue
                # 檔名 / file path 命中 absolute path 規則：行內寫死的才算
                findings.append(Finding(
                    severity=severity,
                    rule=rule_name,
                    file=file_rel,
                    line=line_no,
                    text=line.strip()[:120],
                    suggestion=suggestion,
                ))
    return findings


def scan_path(skill_path: Path, allowlist: set[str]) -> list[Finding]:
    findings: list[Finding] = []
    for fp in iter_files(skill_path):
        try:
            text = fp.read_text(encoding="utf-8")
        except Exception:
            continue
        rel = str(fp.relative_to(skill_path))
        findings.extend(scan_text(text, rel, allowlist))
    return findings


def check_required_files(skill_path: Path) -> list[Finding]:
    findings: list[Finding] = []
    for required in REQUIRED_FILES:
        if not (skill_path / required).exists():
            findings.append(Finding(
                severity="WARN",
                rule="required_file_missing",
                file=required,
                line=0,
                text=f"{required} 不存在於 {skill_path.name}/",
                suggestion=f"加入 {required}（可從別的 skill 複製）",
            ))
    return findings


def get_staged_files() -> list[Path]:
    """取得 git staged files 的 path（給 pre-commit 用）。"""
    try:
        r = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            capture_output=True, text=True, check=True,
        )
        repo_root = Path(subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        ).stdout.strip())
        return [repo_root / line for line in r.stdout.splitlines() if line]
    except subprocess.CalledProcessError:
        return []


def report(findings: list[Finding]) -> int:
    by_severity: dict[str, list[Finding]] = {"BLOCK": [], "WARN": [], "INFO": []}
    for f in findings:
        by_severity.setdefault(f.severity, []).append(f)

    if not findings:
        print("✅ 全部通過。可以 share。")
        return 0

    icons = {"BLOCK": "🔴", "WARN": "🟡", "INFO": "ℹ️"}
    for sev in ("BLOCK", "WARN", "INFO"):
        items = by_severity.get(sev, [])
        if not items:
            continue
        print(f"\n{icons[sev]} {sev}（{len(items)} 條）")
        # group by rule
        by_rule: dict[str, list[Finding]] = {}
        for it in items:
            by_rule.setdefault(it.rule, []).append(it)
        for rule, hits in by_rule.items():
            print(f"\n  [{rule}] — {hits[0].suggestion}")
            for h in hits[:10]:
                print(f"    {h.file}:{h.line}  {h.text}")
            if len(hits) > 10:
                print(f"    ... 另 {len(hits) - 10} 筆")

    if by_severity["BLOCK"]:
        print(f"\n❌ 發現 {len(by_severity['BLOCK'])} 個 BLOCK 級 PII，必修才能 share。")
        return 1
    print(f"\n⚠️ 只有 WARN / INFO，可 share 但建議修。")
    return 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("path", nargs="?", help="要審查的 skill 目錄")
    p.add_argument("--staged-only", action="store_true", help="只審查 git staged files（pre-commit hook 用）")
    p.add_argument("--allowlist", default=str(DEFAULT_ALLOWLIST), help="allowlist.json 路徑")
    args = p.parse_args()

    allowlist = load_allowlist(Path(args.allowlist))

    if args.staged_only:
        files = get_staged_files()
        findings: list[Finding] = []
        for fp in files:
            if not fp.exists() or fp.suffix.lower() in EXCLUDE_BINARY_EXT:
                continue
            try:
                text = fp.read_text(encoding="utf-8")
            except Exception:
                continue
            try:
                rel = str(fp.relative_to(Path.home() / ".claude"))
            except ValueError:
                rel = str(fp)
            findings.extend(scan_text(text, rel, allowlist))
        sys.exit(report(findings))

    if not args.path:
        p.print_help()
        sys.exit(2)

    skill_path = Path(args.path).expanduser().resolve()
    if not skill_path.exists():
        print(f"❌ 路徑不存在：{skill_path}", file=sys.stderr)
        sys.exit(2)

    print(f"🔍 審查 {skill_path}\n")
    findings = scan_path(skill_path, allowlist)
    findings.extend(check_required_files(skill_path))
    sys.exit(report(findings))


if __name__ == "__main__":
    main()
