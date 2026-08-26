#!/usr/bin/env python3
"""在首頁插入或更新一張卡片，其餘卡片一律不動。

為什麼獨立成一支：首頁是手工策展的——每張卡片的標題與摘要是人寫的。
整份重建會把那些文案洗掉，所以這裡只用精確比對動自己那一張。
"""
import sys, re, os, html, datetime

idx, name, title, desc, meta = sys.argv[1:6]
with open(idx, encoding="utf-8") as f:
    s = f.read()

title = title or name
meta = meta or datetime.date.today().isoformat()
card = (
    f'  <a class="card" href="/{name}">\n'
    f'    <h2>{html.escape(title)}</h2>\n'
    f'    <p>{html.escape(desc)}</p>\n'
    f'    <div class="meta">{html.escape(meta)}</div>\n'
    f'  </a>\n\n'
)

pat = re.compile(r'[ \t]*<a class="card" href="/%s">.*?</a>\n*' % re.escape(name), re.S)
if pat.search(s):
    s = pat.sub(card, s, count=1)
    action = "更新既有卡片"
else:
    m = re.search(r'[ \t]*<a class="card"', s)
    if m:
        pos = m.start()
    else:
        m2 = re.search(r'[ \t]*<footer', s)
        pos = m2.start() if m2 else s.rfind("</div>")
    s = s[:pos] + card + s[pos:]
    action = "新增卡片"

tmp = idx + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    f.write(s)
os.replace(tmp, idx)
print(action)
