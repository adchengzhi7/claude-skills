"""走真的 HTTP：開一個只聽本機的伺服器，用標準庫打它。"""
import http.client
import json
import os
import stat
import threading
import unittest

from helpers import NOW, FakeHome

from office import server


class Clock:
    def __init__(self):
        self.now = NOW

    def __call__(self):
        return self.now


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.home = FakeHome()
        self.addCleanup(self.home.cleanup)
        self.cfg_path = os.path.join(self.home.root, "config.json")
        self.state_path = os.path.join(self.home.root, "state", "state.json")
        self.user_themes = os.path.join(self.home.root, "themes")
        self.tmux_log = os.path.join(self.home.root, "tmux.log")
        # 假的 tmux：把收到的參數記下來；list-panes 回一個 pane
        self.tmux = os.path.join(self.home.root, "fake-tmux")
        with open(self.tmux, "w") as fh:
            fh.write('#!/bin/sh\necho "$@" >> "%s"\nif [ "$1" = "list-panes" ]; then printf "%%%%5\\twork:3\\tshop\\n"; fi\n' % self.tmux_log)
        os.chmod(self.tmux, 0o755)
        self.clock = Clock()

    def start(self, demo=False):
        self.office = server.Office(self.home.paths, self.cfg_path, self.state_path, self.user_themes, demo_mode=demo,
                                    clock=self.clock, alive=lambda pid: True, tmux_bin=self.tmux)
        self.office.refresh()
        self.httpd = server.make_server(self.office, 0)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)

    def req(self, method, path, body=None, headers=None, host=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        h = {"Host": host or "127.0.0.1:%d" % self.port, **(headers or {})}
        conn.request(method, path, body=body.encode("utf-8") if isinstance(body, str) else body, headers=h)
        r = conn.getresponse()
        raw = r.read()
        conn.close()
        ctype = r.getheader("Content-Type") or ""
        return r.status, (json.loads(raw) if ctype.startswith("application/json") else raw.decode("utf-8", "ignore")), r

    def jump(self, pane="%5", headers=None, **kw):
        h = {"Content-Type": "application/json", "X-Session-Office": "1"} if headers is None else headers
        return self.req("POST", "/api/jump", body=json.dumps({"pane": pane}), headers=h, **kw)

    # --- 頁面與檔案 ---
    def test_page_has_csp_and_core_files_load(self):
        self.start(demo=True)
        code, body, r = self.req("GET", "/")
        self.assertEqual(code, 200)
        self.assertIn("default-src 'self'", r.getheader("Content-Security-Policy"))
        self.assertIn("<title>", body)
        for path in ("/web/logic.js", "/web/app.js", "/web/base.css", "/themes/pixel-office/theme.css", "/themes/pixel-office/theme.js"):
            self.assertEqual(self.req("GET", path)[0], 200, path)

    def test_cannot_escape_web_or_theme_folders(self):
        self.start(demo=True)
        for path in ("/web/../run.py", "/web/index.html.bak", "/themes/../office/server.py", "/themes/pixel-office/..%2f..%2frun.py",
                     "/themes/pixel-office/theme.py", "/themes/PIXEL/theme.css", "/run.py"):
            self.assertEqual(self.req("GET", path)[0], 404, path)

    def test_theme_route_only_serves_theme_files(self):
        os.makedirs(os.path.join(self.user_themes, "my-look"))
        for name in ("theme.js", "notes.txt", "secret.json"):
            with open(os.path.join(self.user_themes, "my-look", name), "w") as fh:
                fh.write("x")
        self.start(demo=True)
        self.assertEqual(self.req("GET", "/themes/my-look/theme.js")[0], 200)  # 對照組：外觀包的檔拿得到
        # 這些檔案真的存在，但不是外觀包該給的東西（上一層的 README、run.py、資料夾裡的其他檔）
        for path in ("/themes/../README.md", "/themes/../run.py", "/themes/my-look/notes.txt", "/themes/my-look/secret.json", "/themes/./theme.js"):
            self.assertEqual(self.req("GET", path)[0], 404, path)
        self.assertIsNone(self.office.theme_file("..", "run.py"))
        self.assertIsNone(self.office.theme_file("pixel-office", "../../run.py"))
        self.assertIsNone(self.office.theme_file("my-look", "notes.txt"))
        self.assertTrue(self.office.theme_file("pixel-office", "theme.css"))

    def test_user_theme_is_listed_and_served(self):
        os.makedirs(os.path.join(self.user_themes, "my-look"))
        with open(os.path.join(self.user_themes, "my-look", "theme.js"), "w") as fh:
            fh.write("window.SESSION_OFFICE_THEME = {};")
        self.start(demo=True)
        code, body, _ = self.req("GET", "/api/themes")
        self.assertEqual(code, 200)
        self.assertIn("my-look", body["themes"])
        self.assertIn("pixel-office", body["themes"])  # 對照組：內建的也在
        self.assertEqual(self.req("GET", "/themes/my-look/theme.js")[1], "window.SESSION_OFFICE_THEME = {};")

    # --- 只收本機 ---
    def test_foreign_host_header_is_refused(self):
        self.start(demo=True)
        self.assertEqual(self.req("GET", "/api/agents")[0], 200)  # 對照組：正常的 Host 會過
        for path in ("/", "/api/agents", "/api/themes"):
            self.assertEqual(self.req("GET", path, host="evil.example:%d" % self.port)[0], 403, path)
        self.assertEqual(self.jump(host="evil.example")[0], 403)

    # --- 資料 ---
    def test_missing_claude_folder_is_503_not_empty_office(self):
        os.rmdir(self.home.paths["sessions"])
        self.start()
        code, body, _ = self.req("GET", "/api/agents")
        self.assertEqual(code, 503)
        self.assertIn("找不到", body["error"])

    def test_real_empty_is_200_with_zero_sessions(self):
        self.start()
        code, body, _ = self.req("GET", "/api/agents")
        self.assertEqual((code, body["sessions"]), (200, []))

    def test_sessions_and_config_reach_the_page(self):
        self.home.proc(101, status="busy")
        with open(self.cfg_path, "w") as fh:
            json.dump({"groups": [{"name": "店", "color": "#123456", "match": "shop"}]}, fh)
        self.start()
        code, body, _ = self.req("GET", "/api/agents?theme=pixel-office")
        self.assertEqual(code, 200)
        self.assertEqual([(s["state"], s["pane"]) for s in body["sessions"]], [("running", "%5")])
        self.assertEqual(body["config"]["groups"][0]["name"], "店")
        self.assertTrue(body["ui"].isdigit() and int(body["ui"]) > 0)

    def test_broken_config_is_shown_not_ignored(self):
        self.home.proc(101)
        with open(self.cfg_path, "w") as fh:
            fh.write("{ 壞掉")
        self.start()
        code, body, _ = self.req("GET", "/api/agents")
        self.assertEqual(code, 503)
        self.assertIn("設定檔有錯", body["error"])

    def test_state_file_is_private(self):
        self.home.proc(101)
        self.start()
        self.assertEqual(stat.S_IMODE(os.stat(self.state_path).st_mode), 0o600)

    # --- 切視窗 ---
    def test_jump_runs_only_select_window_on_that_pane(self):
        self.home.proc(101)
        self.start()
        code, body, _ = self.jump("%5")
        self.assertEqual((code, body), (200, {"ok": True, "pane": "%5"}))
        with open(self.tmux_log) as fh:
            calls = [line.strip() for line in fh if not line.startswith("list-panes")]
        self.assertEqual(calls, ["select-window -t %5"])

    def test_jump_needs_page_header_and_same_origin(self):
        self.home.proc(101)
        self.start()
        self.assertEqual(self.jump(headers={"Content-Type": "application/json"})[0], 403)
        evil = {"Content-Type": "application/json", "X-Session-Office": "1", "Origin": "https://evil.example"}
        self.assertEqual(self.jump(headers=evil)[0], 403)
        good = {"Content-Type": "application/json", "X-Session-Office": "1", "Origin": "http://127.0.0.1:%d" % self.port}
        self.assertEqual(self.jump(headers=good)[0], 200)  # 對照組

    def test_jump_refuses_unknown_or_malformed_target(self):
        self.home.proc(101)
        self.start()
        for pane in ("%6", "work:3", "%5; kill-server", "", None, 5):
            self.assertEqual(self.jump(pane)[0], 400, pane)
        with open(self.tmux_log) as fh:  # list-panes 有被呼叫（對照組：假 tmux 真的有在記），但沒有任何切視窗
            log = fh.read()
        self.assertIn("list-panes", log)
        self.assertNotIn("select-window", log)

    def test_jump_refuses_stale_data(self):
        self.home.proc(101)
        self.start()
        self.clock.now = NOW + 61
        code, body, _ = self.jump("%5")
        self.assertEqual(code, 503)
        self.assertIn("太舊", body["error"])

    def test_jump_refuses_garbage_body(self):
        self.home.proc(101)
        self.start()
        h = {"Content-Type": "application/json", "X-Session-Office": "1"}
        self.assertEqual(self.req("POST", "/api/jump", body="不是 json", headers=h)[0], 400)
        self.assertEqual(self.req("POST", "/api/jump", body="x" * 2000, headers=h)[0], 400)
        self.assertEqual(self.req("POST", "/api/other", body="{}", headers=h)[0], 404)

    def test_demo_mode_never_touches_tmux(self):
        self.start(demo=True)
        code, body, _ = self.req("GET", "/api/agents")
        self.assertTrue(body["demo"] and len(body["sessions"]) >= 9)
        self.assertEqual(self.jump("%1")[0], 409)
        self.assertFalse(os.path.exists(self.tmux_log))
        self.assertFalse(os.path.exists(self.state_path))

    # --- 審查後補的 ---
    def test_every_kind_of_response_carries_csp_and_refuses_framing(self):
        self.start(demo=True)
        paths = ["/", "/web/app.js", "/web/base.css", "/themes/pixel-office/theme.css", "/themes/pixel-office/theme.js",
                 "/api/agents", "/api/themes", "/favicon.ico", "/no-such-page"]
        for path in paths:
            r = self.req("GET", path)[2]
            csp = r.getheader("Content-Security-Policy") or ""
            for must in ("default-src 'self'", "frame-ancestors 'none'", "object-src 'none'", "frame-src 'none'"):
                self.assertIn(must, csp, path)
            self.assertEqual(r.getheader("X-Frame-Options"), "DENY", path)
            self.assertEqual(r.getheader("Cross-Origin-Resource-Policy"), "same-origin", path)
            self.assertNotIn("sandbox", csp, path)  # 一般檔案不加 sandbox（加了頁面自己的程式也跑不了）
        refused = self.req("GET", "/api/agents", host="evil.example")[2]
        self.assertIn("default-src 'self'", refused.getheader("Content-Security-Policy") or "")

    def test_svg_from_a_theme_is_sandboxed(self):
        os.makedirs(os.path.join(self.user_themes, "my-look"))
        for name, body in (("theme.js", "x"), ("deco.svg", '<svg xmlns="http://www.w3.org/2000/svg"><script>document.title="跑了"</script></svg>')):
            with open(os.path.join(self.user_themes, "my-look", name), "w") as fh:
                fh.write(body)
        self.start(demo=True)
        code, _, r = self.req("GET", "/themes/my-look/deco.svg")
        self.assertEqual((code, r.getheader("Content-Type")), (200, "image/svg+xml"))
        csp = r.getheader("Content-Security-Policy")
        self.assertIn("sandbox", csp.split("; "))  # 被當成文件打開時，裡面的程式不准跑
        self.assertIn("default-src 'self'", csp)

    def test_symlinked_file_inside_a_theme_is_not_served(self):
        secret = os.path.join(self.home.root, "secret.txt")
        with open(secret, "w") as fh:
            fh.write("私鑰")
        look = os.path.join(self.user_themes, "my-look")
        os.makedirs(look)
        with open(os.path.join(look, "theme.js"), "w") as fh:
            fh.write("ok")
        os.symlink(secret, os.path.join(look, "k.js"))
        os.symlink("../../secret.txt", os.path.join(look, "k2.css"))
        self.start(demo=True)
        self.assertEqual(self.req("GET", "/themes/my-look/theme.js")[:2], (200, "ok"))  # 對照組：真的檔案拿得到
        for name in ("k.js", "k2.css"):
            code, body, _ = self.req("GET", "/themes/my-look/" + name)
            self.assertEqual(code, 404, name)
            self.assertNotIn("私鑰", json.dumps(body, ensure_ascii=False))

    def test_theme_folder_itself_may_be_a_symlink(self):
        real = os.path.join(self.home.root, "dev", "my-look")
        os.makedirs(real)
        with open(os.path.join(real, "theme.js"), "w") as fh:
            fh.write("dev 版")
        os.makedirs(self.user_themes)
        os.symlink(real, os.path.join(self.user_themes, "my-look"))
        self.start(demo=True)
        self.assertEqual(self.req("GET", "/themes/my-look/theme.js")[:2], (200, "dev 版"))

    def test_half_a_character_in_a_name_does_not_take_the_page_down(self):
        self.home.proc(101, status="busy", name="壞字\ud83d結尾", nameSource="user")
        self.start()
        code, body, _ = self.req("GET", "/api/agents")
        self.assertEqual(code, 200)
        self.assertEqual(len(body["sessions"]), 1)
        self.assertTrue(body["sessions"][0]["name"].startswith("壞字"))
        self.assertTrue(os.path.exists(self.state_path))

    def test_jump_refuses_null_origin_and_there_is_no_cors(self):
        self.home.proc(101)
        self.start()
        h = {"Content-Type": "application/json", "X-Session-Office": "1", "Origin": "null"}
        self.assertEqual(self.jump(headers=h)[0], 403)
        code, _, r = self.req("OPTIONS", "/api/jump", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
        self.assertGreaterEqual(code, 400)
        self.assertIsNone(r.getheader("Access-Control-Allow-Origin"))
        self.assertIsNone(self.req("GET", "/api/agents", headers={"Origin": "https://evil.example"})[2].getheader("Access-Control-Allow-Origin"))

    def test_memory_file_that_cannot_be_written_does_not_blank_the_page(self):
        self.home.proc(101, status="busy")
        blocker = os.path.join(self.home.root, "state")
        with open(blocker, "w") as fh:  # 把「該是資料夾」的位置佔成一個檔，記憶檔就寫不進去
            fh.write("x")
        self.start()
        code, body, _ = self.req("GET", "/api/agents")
        self.assertEqual((code, len(body["sessions"])), (200, 1))
        self.assertIn("記憶檔寫不進去", body["warnings"][0])

    def test_broken_memory_file_on_disk_is_ignored(self):
        self.home.proc(101, status="busy")
        os.makedirs(os.path.dirname(self.state_path))
        with open(self.state_path, "w") as fh:
            fh.write('["不是", "我們的格式"]')
        self.start()
        code, body, _ = self.req("GET", "/api/agents")
        self.assertEqual((code, body["sessions"][0]["state"], body["warnings"]), (200, "running", []))

    def test_demo_countdown_actually_counts_down(self):
        self.start(demo=True)
        first = next(s for s in self.req("GET", "/api/agents")[1]["sessions"] if s["id"] == "demo-02")["cacheExpiresAt"]
        self.clock.now = NOW + 100
        self.office.refresh()
        body = self.req("GET", "/api/agents")[1]
        self.assertEqual(next(s for s in body["sessions"] if s["id"] == "demo-02")["cacheExpiresAt"], first)
        self.assertEqual(body["generatedAt"], NOW + 100)

    # --- 第五輪審查後補的 ---
    def strict(self, path):
        """用瀏覽器的標準解 JSON：出現 NaN／Infinity 就算失敗（Python 預設會放過，瀏覽器不會）。"""
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", path, headers={"Host": "127.0.0.1:%d" % self.port})
        r = conn.getresponse()
        raw = r.read().decode("utf-8")
        conn.close()

        def refuse(name):
            raise AssertionError("瀏覽器解不開的值：" + name)
        return r.status, json.loads(raw, parse_constant=refuse)

    def test_numbers_a_browser_cannot_parse_never_reach_the_page(self):
        self.home.proc(101, status="busy", statusUpdatedAt=float("inf"))
        self.home.proc(102, sid="test-session-bbbb", status="idle", startedAt=float("nan"), tmux="work:@2.%6")
        self.start()
        code, body = self.strict("/api/agents")
        self.assertEqual((code, len(body["sessions"])), (200, 2))
        self.home.proc(103, sid="test-session-cccc", status="busy")  # 對照組：正常的照常
        self.office.refresh()
        self.assertEqual(sorted(s["state"] for s in self.strict("/api/agents")[1]["sessions"] if s["id"] == "test-session-cccc"), ["running"])

    def test_memory_with_wrong_inner_types_is_thrown_away_once_and_says_so(self):
        self.home.proc(101, status="busy")
        os.makedirs(os.path.dirname(self.state_path))
        for inner in ({"lastSeen": "字串"}, {"lastSeen": NOW, "endedAt": "字串"}):
            with open(self.state_path, "w") as fh:
                json.dump({"v": 1, "transcripts": {}, "tpaths": {}, "seen": {"test-session-dddd": inner}}, fh)
            self.office = server.Office(self.home.paths, self.cfg_path, self.state_path, self.user_themes, clock=self.clock,
                                        alive=lambda pid: True, tmux_bin=self.tmux)
            first = self.office.refresh()
            self.assertTrue(first["ok"], first)
            self.assertEqual(len(first["data"]["sessions"]), 1)
            self.assertIn("記憶有問題", first["data"]["warnings"][0])
            self.assertRegex(first["data"]["warnings"][0], r"（\w+Error）")  # 講得出是哪一種錯，事後才查得到
            second = self.office.refresh()  # 記憶已經換成乾淨的，下一輪不再提醒
            self.assertEqual((second["ok"], second["data"]["warnings"]), (True, []))


if __name__ == "__main__":
    unittest.main()
