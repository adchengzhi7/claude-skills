"""用真的 tmux 驗一次「點卡片真的會切視窗」。開一個獨立的 tmux 伺服器（-L 另一個 socket），不會動到你正在用的 tmux。"""
import json
import os
import subprocess
import unittest

from helpers import NOW, SID, FakeHome

from office import server, tmuxio

REAL_TMUX = tmuxio.find_tmux()


@unittest.skipUnless(REAL_TMUX, "這台沒裝 tmux，跳過")
class RealTmuxTest(unittest.TestCase):
    def setUp(self):
        self.home = FakeHome()
        self.addCleanup(self.home.cleanup)
        self.sock = "session-office-test-%d" % os.getpid()
        self.tmux = os.path.join(self.home.root, "tmux-isolated")
        with open(self.tmux, "w") as fh:
            fh.write('#!/bin/sh\nexec "%s" -L "%s" "$@"\n' % (REAL_TMUX, self.sock))
        os.chmod(self.tmux, 0o755)
        # kill-server 不會刪 socket 檔，自己收（清理是倒著跑的：先 kill 再刪）
        sock_file = os.path.join(os.environ.get("TMUX_TMPDIR") or "/tmp", "tmux-%d" % os.getuid(), self.sock)
        self.addCleanup(lambda: os.path.exists(sock_file) and os.remove(sock_file))
        self.addCleanup(subprocess.run, [self.tmux, "kill-server"], capture_output=True)
        subprocess.run([self.tmux, "new-session", "-d", "-s", "t", "-n", "first"], check=True, capture_output=True)
        subprocess.run([self.tmux, "new-window", "-d", "-t", "t", "-n", "second"], check=True, capture_output=True)

    def active_window(self):
        return subprocess.run([self.tmux, "display-message", "-p", "-t", "t", "#{window_name}"], capture_output=True, text=True).stdout.strip()

    def test_click_really_switches_the_window(self):
        panes = tmuxio.list_panes(self.tmux)
        pane = next(p for p, (_where, name) in panes.items() if name == "second")
        self.home.proc(101, tmux="t:@1." + pane)
        office = server.Office(self.home.paths, os.path.join(self.home.root, "config.json"), os.path.join(self.home.root, "state.json"),
                               os.path.join(self.home.root, "themes"), clock=lambda: NOW, alive=lambda pid: True, tmux_bin=self.tmux)
        snap = office.refresh()
        row = next(s for s in snap["data"]["sessions"] if s["id"] == SID)
        self.assertEqual((row["pane"], row["windowName"]), (pane, "second"))
        self.assertEqual(self.active_window(), "first")  # 對照組：切之前畫面在另一個視窗
        code, body = office.jump(pane)
        self.assertEqual((code, body), (200, {"ok": True, "pane": pane}), json.dumps(body, ensure_ascii=False))
        self.assertEqual(self.active_window(), "second")

    def test_closed_window_fails_loudly(self):
        panes = tmuxio.list_panes(self.tmux)
        pane = next(p for p, (_where, name) in panes.items() if name == "second")
        self.home.proc(101, tmux="t:@1." + pane)
        office = server.Office(self.home.paths, os.path.join(self.home.root, "config.json"), os.path.join(self.home.root, "state.json"),
                               os.path.join(self.home.root, "themes"), clock=lambda: NOW, alive=lambda pid: True, tmux_bin=self.tmux)
        office.refresh()
        subprocess.run([self.tmux, "kill-window", "-t", "t:second"], check=True, capture_output=True)
        code, body = office.jump(pane)  # 資料還是舊的（視窗剛被關），切不過去要講出來
        self.assertEqual(code, 409)
        self.assertIn("切換失敗", body["error"])
        self.assertEqual(self.active_window(), "first")

    def test_no_tmux_server_running_is_unknown_not_empty(self):
        subprocess.run([self.tmux, "kill-server"], capture_output=True)
        self.assertIsNone(tmuxio.list_panes(self.tmux))

    def test_window_name_that_is_not_valid_utf8_does_not_break_the_office(self):
        subprocess.run([self.tmux.encode(), b"new-window", b"-d", b"-t", b"t", b"-n", b"caf\xe9"], check=True, capture_output=True)
        panes = tmuxio.list_panes(self.tmux)
        self.assertIsInstance(panes, dict)
        self.assertEqual(len(panes), 3)  # 對照組：原本兩個視窗加上這個怪名字的，三個都列得出來
        self.assertTrue(any(name.startswith("caf") for _where, name in panes.values()))


if __name__ == "__main__":
    unittest.main()
