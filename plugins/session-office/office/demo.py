"""示範資料：每一種狀態各一張卡。做外觀包、截圖、第一次試用時用（--demo），不會讀到任何真實對話。"""


def payload(now, started=None):
    """started＝示範開始的時間：快取倒數以它為準往下數（不然每次整理都重設，倒數永遠不動）。"""
    t0 = now if started is None else started

    def row(i, state, name, project, mins, **extra):
        base = {"id": "demo-%02d" % i, "state": state, "since": now - mins * 60, "project": project, "path": "~/Projects/" + project,
                "tmux": "work:%d" % i, "pane": "%%%d" % i, "windowName": project, "name": name, "helpers": 0, "model": "demo",
                "context": 80, "contextEstimated": True, "lastUser": "", "lastReport": "", "question": "", "turns": 3,
                "started": now - 7200, "lastActivity": now - mins * 60,
                "cacheExpiresAt": t0 + 3000, "ctxTokens": 64000, "cacheTtl": 3600}
        return {**base, **extra}

    sessions = [
        row(1, "waiting_question", "官網改版-首頁", "website", 4, question="主視覺要用 A 版還是 B 版？", context=62),
        row(2, "waiting_permission", "報表-月結匯出", "reports", 2, question="想用 Bash：npm run export -- --month 2026-09", context=45,
            cacheExpiresAt=t0 + 420, ctxTokens=312000),
        row(3, "ball", "客服信-退貨流程", "support", 9, lastReport="現在球在你這裡的是：退貨期限要寫 7 天還是 14 天", context=71),
        row(4, "running", "訂單系統-修 bug", "orders", 6, context=58),
        row(5, "helpers", "資料整理-舊客戶名單", "data-cleanup", 12, helpers=3, context=24),
        row(6, "reported", "會議記錄-週會", "notes", 25, lastReport="整理好了，三個待辦已列在最後一段。", context=88),
        row(7, "reported", "部落格-十月文章", "blog", 95, lastReport="初稿寫完，等你有空看。", context=40,
            cacheExpiresAt=t0 - 1500, ctxTokens=156000),
        row(8, "idle", "", "sandbox", 1, context=None, cacheExpiresAt=None),
        row(9, "running", "匯入工具-跑很久", "importer", 75, context=33,
            trouble={"kind": "stuck", "text": "顯示在跑，但已 75 分鐘沒有任何動靜", "since": now - 75 * 60}),
        {"id": "demo-10", "state": "ended", "since": now - 3 * 3600, "project": "old-task", "path": "~/Projects/old-task",
         "tmux": "", "pane": "", "windowName": "", "name": "已經關掉的那個", "helpers": 0},
    ]
    return {"generatedAt": now, "sessions": sessions, "skipped": 0, "warnings": [], "sources": {"tmux": True, "moshi": False}, "demo": True}


DEMO_CONFIG = {
    "groups": [
        {"name": "網站", "color": "#7048e8", "match": "website|blog"},
        {"name": "營運", "color": "#d9480f", "match": "reports|orders|support|importer"},
    ],
    "mark": {"label": "重要", "match": "月結|bug"},
    "ballPhrases": ["現在球在你這裡的是："],
}
