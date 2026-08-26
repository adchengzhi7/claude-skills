#!/usr/bin/env python3
"""產生 previews/_pages.json — 站上所有頁面與附件的清單。

給 index.html 的 Cmd+K 搜尋與「未分類頁面」區塊用。
為什麼要這支：index.html 是手工策展的卡片清單，發佈失敗或手動丟進來的檔案
不會有卡片 → 在首頁上等於不存在。這份清單讓那些頁面仍然找得到。
"""
import os, json, datetime, sys

root = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/previews")
EXT = (".html", ".htm", ".pdf")
rows = []
for e in sorted(os.listdir(root)):
    if e.startswith(".") or e == "index.html":
        continue
    if not e.lower().endswith(EXT):
        continue
    p = os.path.join(root, e)
    if not os.path.isfile(p):
        continue
    st = os.stat(p)
    rows.append({
        "f": e,
        "t": datetime.date.fromtimestamp(st.st_mtime).isoformat(),
        "s": st.st_size,
    })
rows.sort(key=lambda r: r["t"], reverse=True)
out = os.path.join(root, "_pages.json")
tmp = out + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(rows, f, ensure_ascii=False, separators=(",", ":"))
os.replace(tmp, out)
print(f"_pages.json：{len(rows)} 筆")
