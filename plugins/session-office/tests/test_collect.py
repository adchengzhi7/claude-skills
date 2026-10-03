import json
import os
import unittest

from helpers import NOW, SID, FakeHome, assistant, cfg, human, tool_result

from office import collect

SID2 = "test-session-bbbb"
ALIVE = {101, 102}


def alive(pid):
    return int(pid) in ALIVE


class CollectTest(unittest.TestCase):
    def setUp(self):
        self.home = FakeHome()
        self.addCleanup(self.home.cleanup)

    def run_once(self, state=None, now=NOW, panes="default", live=alive, **cfg_over):
        table = {"%5": ("work:3", "shop-window")} if panes == "default" else panes
        return collect.collect(now, cfg(**cfg_over), self.home.paths, state, alive=live, list_panes=lambda: table)

    def one(self, **kw):
        data, state = self.run_once(**kw)
        rows = [s for s in data["sessions"] if s["id"] == SID]
        self.assertEqual(len(rows), 1, data)
        return rows[0], data, state

    # --- 整份拿不到 vs 剛好沒有：兩種不能長一樣 ---
    def test_missing_sessions_dir_is_an_error_not_zero(self):
        os.rmdir(self.home.paths["sessions"])
        with self.assertRaises(collect.CollectError):
            self.run_once()

    def test_empty_sessions_dir_is_a_real_zero(self):
        data, _ = self.run_once()
        self.assertEqual((data["sessions"], data["skipped"]), ([], 0))

    def test_unreadable_file_is_counted_and_others_still_show(self):
        self.home.proc(101)
        with open(os.path.join(self.home.paths["sessions"], "999.json"), "w") as fh:
            fh.write("{ 壞掉的")
        row, data, _ = self.one()
        self.assertEqual(data["skipped"], 1)
        self.assertEqual(row["id"], SID)

    # --- 狀態 ---
    def test_busy_is_running(self):
        self.home.proc(101, status="busy")
        self.assertEqual(self.one()[0]["state"], "running")

    def test_waiting_with_question(self):
        self.home.proc(101, status="waiting", waitingFor="input needed")
        self.home.transcript([human("開始", NOW - 90), assistant(NOW - 80, tool=("t1", "AskUserQuestion", {"questions": [{"question": "要 A 還是 B？"}]}))])
        row = self.one()[0]
        self.assertEqual((row["state"], row["question"]), ("waiting_question", "要 A 還是 B？"))

    def test_waiting_for_permission(self):
        self.home.proc(101, status="waiting")
        self.home.transcript([human("開始", NOW - 90), assistant(NOW - 80, tool=("t1", "Bash", {"command": "git push"}))])
        row = self.one()[0]
        self.assertEqual((row["state"], row["question"]), ("waiting_permission", "想用 Bash：git push"))

    def test_waiting_without_any_pending_tool(self):
        self.home.proc(101, status="waiting")
        row = self.one()[0]
        self.assertEqual((row["state"], row["question"]), ("waiting_question", ""))

    def test_idle_with_reply_is_reported(self):
        self.home.proc(101, status="idle")
        self.home.transcript([human("開始", NOW - 90), assistant(NOW - 80, text="做完了")])
        row = self.one()[0]
        self.assertEqual((row["state"], row["lastReport"], row["turns"]), ("reported", "做完了", 1))

    def test_shell_status_counts_as_stopped(self):
        self.home.proc(101, status="shell")
        self.home.transcript([human("開始", NOW - 90), assistant(NOW - 80, text="做完了")])
        self.assertEqual(self.one()[0]["state"], "reported")

    def test_new_session_without_transcript_is_idle(self):
        self.home.proc(101, status="idle")
        row = self.one()[0]
        self.assertEqual((row["state"], row["context"]), ("idle", None))
        self.assertNotIn("cacheExpiresAt", row)

    def test_ball_phrase_only_when_configured(self):
        self.home.proc(101, status="idle")
        self.home.transcript([human("開始", NOW - 90), assistant(NOW - 80, text="現在球在你這裡的是：選 A 或 B")])
        self.assertEqual(self.one()[0]["state"], "reported")  # 對照組：沒設定就不是
        self.assertEqual(self.one(ballPhrases=["現在球在你這裡"])[0]["state"], "ball")

    def test_helpers_outside(self):
        self.home.proc(101, status="idle")
        self.home.transcript([human("開始", NOW - 90), assistant(NOW - 80, text="派出去了"),
                              tool_result("t1", NOW - 70, result={"status": "async_launched", "agentId": "abc123"})])
        row = self.one()[0]
        self.assertEqual((row["state"], row["helpers"]), ("helpers", 1))

    def test_unknown_status_is_passed_through_loudly(self):
        self.home.proc(101, status="hibernating")
        self.assertEqual(self.one()[0]["state"], "unknown:hibernating")

    # --- 急診室 ---
    def test_error_message_is_trouble(self):
        self.home.proc(101, status="idle")
        self.home.transcript([human("開始", NOW - 90), assistant(NOW - 50, text="API Error: 401", model="<synthetic>", isApiErrorMessage=True)])
        self.assertEqual(self.one()[0]["trouble"]["kind"], "error")

    def test_error_followed_by_real_reply_is_fine(self):
        self.home.proc(101, status="idle")
        self.home.transcript([human("開始", NOW - 90), assistant(NOW - 50, text="API Error: 401", model="<synthetic>", isApiErrorMessage=True),
                              assistant(NOW - 20, text="好了")])
        self.assertNotIn("trouble", self.one()[0])

    def test_running_but_silent_for_over_an_hour_is_stuck(self):
        self.home.proc(101, status="busy", statusUpdatedAt=(NOW - 2 * 3600) * 1000)
        path = self.home.transcript([human("開始", NOW - 2 * 3600)])
        os.utime(path, (NOW - 2 * 3600, NOW - 2 * 3600))
        self.assertEqual(self.one()[0]["trouble"]["kind"], "stuck")
        os.utime(path, (NOW - 60, NOW - 60))  # 對照組：一分鐘前還有寫入＝不是卡住
        self.assertNotIn("trouble", self.one()[0])

    # --- 已關閉 ---
    def test_dead_process_is_not_listed_when_never_seen(self):
        self.home.proc(555, status="busy")
        data, _ = self.run_once()
        self.assertEqual(data["sessions"], [])

    def test_seen_idle_then_gone_is_plain_ended(self):
        self.home.proc(101, status="idle")
        _, _, state = self.one()
        row, _, _ = self.one(state=state, now=NOW + 5, live=lambda pid: False)
        self.assertEqual(row["state"], "ended")
        self.assertNotIn("trouble", row)

    def test_seen_busy_then_gone_right_away_is_crashed(self):
        self.home.proc(101, status="busy")
        _, _, state = self.one()
        row, _, state2 = self.one(state=state, now=NOW + 5, live=lambda pid: False)
        self.assertEqual((row["state"], row["trouble"]["kind"]), ("ended", "crashed"))
        row3, _, _ = self.one(state=state2, now=NOW + 3600, live=lambda pid: False)  # 之後幾輪還是記得它是當掉的
        self.assertEqual(row3["trouble"]["kind"], "crashed")

    def test_seen_busy_long_ago_is_not_called_crashed(self):
        self.home.proc(101, status="busy")
        _, _, state = self.one()
        row, _, _ = self.one(state=state, now=NOW + 3 * 3600, live=lambda pid: False)
        self.assertEqual(row["state"], "ended")
        self.assertNotIn("trouble", row)

    def test_ended_forgotten_after_12_hours(self):
        self.home.proc(101, status="idle")
        _, _, state = self.one()
        _, state = self.run_once(state=state, now=NOW + 60, live=lambda pid: False)
        data, state = self.run_once(state=state, now=NOW + 13 * 3600, live=lambda pid: False)
        self.assertEqual(data["sessions"], [])
        self.assertEqual(state["seen"], {})

    def test_session_that_comes_back_is_live_again(self):
        self.home.proc(101, status="idle")
        _, _, state = self.one()
        _, state = self.run_once(state=state, now=NOW + 5, live=lambda pid: False)
        row, _, _ = self.one(state=state, now=NOW + 10)
        self.assertEqual(row["state"], "idle")

    # --- tmux ---
    def test_pane_found_is_clickable(self):
        self.home.proc(101)
        row, data, _ = self.one()
        self.assertEqual((row["pane"], row["tmux"], row["windowName"]), ("%5", "work:3", "shop-window"))
        self.assertTrue(data["sources"]["tmux"])

    def test_no_tmux_means_not_clickable_and_not_trouble(self):
        self.home.proc(101)
        row, data, _ = self.one(panes=None)
        self.assertEqual((row["pane"], row["tmux"]), ("", ""))
        self.assertNotIn("trouble", row)
        self.assertFalse(data["sources"]["tmux"])

    def test_pane_closed_is_not_clickable(self):
        self.home.proc(101)
        self.assertEqual(self.one(panes={"%9": ("work:1", "other")})[0]["pane"], "")

    # --- context ---
    def usage_transcript(self, tokens):
        self.home.transcript([human("開始", NOW - 90), assistant(NOW - 80, text="好", usage={"input_tokens": tokens})])

    def test_context_estimated_from_tokens(self):
        self.home.proc(101)
        self.usage_transcript(50_000)
        row = self.one()[0]
        self.assertEqual((row["context"], row["contextEstimated"]), (75, True))

    def test_context_window_from_settings_1m(self):
        self.home.proc(101)
        self.usage_transcript(50_000)
        with open(self.home.paths["settings"], "w") as fh:
            json.dump({"model": "opus[1m]"}, fh)
        self.assertEqual(self.one()[0]["context"], 95)

    def test_context_over_200k_must_be_large_window(self):
        self.home.proc(101)
        self.usage_transcript(300_000)
        self.assertEqual(self.one()[0]["context"], 70)

    def test_context_window_fixed_by_config(self):
        self.home.proc(101)
        self.usage_transcript(50_000)
        self.assertEqual(self.one(contextWindow=500_000)[0]["context"], 90)

    def test_moshi_number_wins_when_installed(self):
        self.home.proc(101)
        self.usage_transcript(50_000)
        os.makedirs(self.home.paths["moshi"])
        with open(os.path.join(self.home.paths["moshi"], SID + ".json"), "w") as fh:
            json.dump({"contextRemaining": 42}, fh)
        row, data, _ = self.one()
        self.assertEqual((row["context"], row["contextEstimated"]), (42, False))
        self.assertTrue(data["sources"]["moshi"])

    def test_moshi_installed_but_no_number_falls_back_to_estimate(self):
        self.home.proc(101)
        self.usage_transcript(50_000)
        os.makedirs(self.home.paths["moshi"])
        with open(os.path.join(self.home.paths["moshi"], SID + ".json"), "w") as fh:
            json.dump({"contextRemaining": "壞掉"}, fh)
        row = self.one()[0]
        self.assertEqual((row["context"], row["contextEstimated"]), (75, True))

    # --- 其他 ---
    def test_cache_countdown(self):
        self.home.proc(101)
        self.home.transcript([human("開始", NOW - 90), assistant(NOW - 80, text="好", usage={"input_tokens": 1000, "cache_creation": {"ephemeral_1h_input_tokens": 5}})])
        row = self.one()[0]
        self.assertEqual((row["cacheExpiresAt"], row["ctxTokens"], row["cacheTtl"]), (NOW - 80 + 3600, 1000, 3600))

    def test_name_priority(self):
        self.home.proc(101)
        self.home.transcript([{"type": "ai-title", "aiTitle": "整理月結"}])
        self.assertEqual(self.one()[0]["name"], "整理月結")
        self.home.proc(101, name="我自己取的", nameSource="user")
        self.assertEqual(self.one()[0]["name"], "我自己取的")

    def test_project_and_home(self):
        self.home.proc(101)
        row = self.one()[0]
        self.assertEqual((row["project"], row["path"]), ("shop", "~/Projects/shop"))
        self.home.proc(101, cwd=self.home.root)
        self.assertEqual(self.one()[0]["project"], "~（家目錄）")

    def test_two_sessions_and_incremental_state(self):
        self.home.proc(101, status="idle")
        self.home.proc(102, sid=SID2, status="busy", tmux="work:@2.%6")
        path = self.home.transcript([human("第一句", NOW - 90), assistant(NOW - 80, text="一")])
        data, state = self.run_once()
        self.assertEqual(sorted(s["state"] for s in data["sessions"]), ["reported", "running"])
        self.home.transcript([human("第二句", NOW - 10)], append=True)
        data, state = self.run_once(state=state, now=NOW + 1)
        row = next(s for s in data["sessions"] if s["id"] == SID)
        self.assertEqual((row["lastUser"], row["turns"]), ("第二句", 2))
        self.assertEqual(state["tpaths"][SID], path)

    def test_bad_session_id_is_skipped(self):
        self.home.proc(101, sid="../../etc/passwd")
        data, _ = self.run_once()
        self.assertEqual((data["sessions"], data["skipped"]), ([], 1))

    # --- 審查後補的：壞掉不能看起來正常 ---
    def test_missing_status_is_loud_unless_just_started(self):
        p = self.home.proc(101)
        del p["status"]
        with open(os.path.join(self.home.paths["sessions"], "101.json"), "w") as fh:
            json.dump(p, fh)
        self.assertEqual(self.one()[0]["state"], "unknown:沒有狀態")
        p["startedAt"] = (NOW - 30) * 1000  # 對照組：剛啟動、還沒來得及寫狀態的不算
        with open(os.path.join(self.home.paths["sessions"], "101.json"), "w") as fh:
            json.dump(p, fh)
        self.assertEqual(self.one()[0]["state"], "idle")

    def test_ball_wins_over_helpers_still_out(self):
        self.home.proc(101, status="idle")
        self.home.transcript([human("開始", NOW - 90), tool_result("t1", NOW - 80, result={"status": "async_launched", "agentId": "abc123"}),
                              assistant(NOW - 70, text="現在球在你這裡的是：選 A 或 B")])
        row = self.one(ballPhrases=["現在球在你這裡"])[0]
        self.assertEqual((row["state"], row["helpers"]), ("ball", 1))
        self.assertEqual(self.one()[0]["state"], "helpers")  # 對照組：沒設定句型時照舊算等幫手

    def test_one_weird_line_does_not_turn_a_live_session_into_ended(self):
        self.home.proc(101, status="busy")
        weird = {"type": "assistant", "timestamp": "x", "message": {"model": "m", "content": [{"type": "text", "text": 123}]}}
        path = self.home.transcript([human("開始", NOW - 90), weird, {"type": "assistant", "message": "字串"}, assistant(NOW - 50, text="還在做")])
        row, data, state = self.one()
        self.assertEqual((row["state"], row["lastReport"]), ("running", "還在做"))
        self.assertNotIn("trouble", row)
        self.assertEqual(state["transcripts"][path]["badLines"], 1)
        self.assertEqual(state["transcripts"][path]["offset"], os.path.getsize(path))  # 有記住讀到哪，下一輪不會從頭重讀
        self.assertEqual(data["warnings"], [])

    def test_session_whose_details_fail_goes_to_er_not_to_ended(self):
        self.home.proc(101, status="busy", startedAt="不是數字")
        row, data, state = self.one()
        self.assertEqual((row["state"], row["trouble"]["kind"], row["pane"]), ("running", "unreadable", "%5"))
        self.assertEqual(state["seen"][SID]["lastSeen"], NOW)
        row2, _, _ = self.one(state=state, now=NOW + 5)  # 下一輪還是活著的那張卡，不會變成「已關閉／當掉」
        self.assertEqual((row2["state"], row2["trouble"]["kind"]), ("running", "unreadable"))

    def test_missing_projects_folder_is_announced(self):
        self.home.proc(101, status="idle")
        self.assertEqual(self.run_once()[0]["warnings"], [])  # 對照組：資料夾在就不叫
        os.rmdir(self.home.paths["projects"])
        data, _ = self.run_once()
        self.assertEqual(len(data["warnings"]), 1)
        self.assertIn("對話紀錄資料夾", data["warnings"][0])
        self.assertEqual(data["sources"]["transcripts"], {"found": 0, "missing": 1})

    def test_all_live_sessions_without_transcript_is_announced(self):
        self.home.proc(101)
        self.assertEqual(self.run_once()[0]["warnings"], [])  # 只有一個找不到：可能只是剛開，不叫
        self.home.proc(102, sid=SID2, tmux="work:@2.%6")
        data, _ = self.run_once()
        self.assertIn("全都找不到對話紀錄", data["warnings"][0])
        self.home.transcript([human("開始", NOW - 9)])
        self.assertEqual(self.run_once()[0]["warnings"], [])  # 找得到一份就不叫

    def test_many_unreadable_lines_are_announced(self):
        self.home.proc(101, status="idle")
        weird = {"type": "assistant", "message": {"model": "m", "content": [{"type": "text", "text": 123}]}}
        self.home.transcript([weird] * 9 + [assistant(NOW - 5, text="好")])
        self.assertEqual(self.run_once()[0]["warnings"], [])  # 9 行還不叫
        self.home.transcript([weird], append=True)
        data, _ = self.run_once()
        self.assertIn("10 行看不懂", data["warnings"][0])

    def test_broken_saved_state_is_reset_not_fatal(self):
        self.home.proc(101, status="busy")
        for broken in ([], {"v": 1}, {"v": 1, "transcripts": [], "tpaths": {}, "seen": {}}, {"v": 1, "transcripts": {}, "tpaths": {}, "seen": {"x": 3}}, "字串"):
            row = self.one(state=broken)[0]
            self.assertEqual(row["state"], "running", broken)

    def test_broken_saved_transcript_summary_is_reset(self):
        self.home.proc(101, status="idle")
        path = self.home.transcript([human("開始", NOW - 90), assistant(NOW - 80, text="做完了")])
        _, _, state = self.one()
        state["transcripts"][path] = {"v": 1, "offset": "壞掉", "agents": [], "pending": {}}
        self.assertEqual(self.one(state=state)[0]["lastReport"], "做完了")

    def test_home_prefix_is_not_confused_with_sibling_folder(self):
        self.home.proc(101, cwd=self.home.root + "2/x")
        self.assertEqual(self.one()[0]["path"], self.home.root + "2/x")

    def test_native_windows_is_refused_before_touching_any_process(self):
        import run
        from unittest import mock
        with mock.patch.object(collect.os, "name", "nt"):
            with self.assertRaises(collect.CollectError):
                collect.pid_alive(1)
            # run.py 要在動任何東西之前就拒絕：不建立辦公室、不讀任何程式清單
            with mock.patch("sys.stderr") as err, mock.patch.object(run.server, "Office") as office:
                self.assertEqual(run.main(["--once"]), 1)
            office.assert_not_called()
            self.assertIn("不支援原生 Windows", "".join(str(c.args[0]) for c in err.write.call_args_list))
        self.assertTrue(collect.pid_alive(os.getpid()))  # 對照組：一般情況照常

    # --- 重審後補的：agent／SDK 開的 session 本來就不寫狀態，不能丟進急診室 ---
    def sdk_proc(self, **extra):
        p = self.home.proc(101, entrypoint="sdk-cli", **extra)
        for k in ("status", "statusUpdatedAt", "updatedAt"):
            p.pop(k, None)
        p.update({k: v for k, v in extra.items() if k in ("status", "statusUpdatedAt", "updatedAt")})
        with open(os.path.join(self.home.paths["sessions"], "101.json"), "w") as fh:
            json.dump(p, fh)

    def test_sdk_session_without_status_is_not_an_emergency(self):
        self.sdk_proc()  # 已經開了一小時、從來沒寫過狀態
        path = self.home.transcript([human("開始", NOW - 900), assistant(NOW - 800, text="做完了")])
        os.utime(path, (NOW - 800, NOW - 800))
        row = self.one()[0]
        self.assertEqual(row["state"], "reported")
        self.assertNotIn("trouble", row)

    def test_sdk_session_writing_right_now_counts_as_running(self):
        self.sdk_proc()
        path = self.home.transcript([human("開始", NOW - 900), assistant(NOW - 20, text="還在做")])
        os.utime(path, (NOW - 20, NOW - 20))
        self.assertEqual(self.one()[0]["state"], "running")
        os.utime(path, (NOW - 600, NOW - 600))  # 對照組：十分鐘沒寫了就不算在跑
        self.assertEqual(self.one()[0]["state"], "reported")

    def test_missing_status_stays_loud_when_the_session_should_have_one(self):
        self.sdk_proc(statusUpdatedAt=(NOW - 60) * 1000)  # 有在追蹤狀態的痕跡，status 卻不見
        self.assertEqual(self.one()[0]["state"], "unknown:沒有狀態")
        p = self.home.proc(101)
        del p["status"], p["entrypoint"]  # 連 entrypoint 都沒有（格式變了）：寧可多叫
        with open(os.path.join(self.home.paths["sessions"], "101.json"), "w") as fh:
            json.dump(p, fh)
        self.assertEqual(self.one()[0]["state"], "unknown:沒有狀態")

    def test_a_few_odd_lines_in_a_long_session_are_not_announced(self):
        self.home.proc(101, status="idle")
        weird = {"type": "assistant", "message": {"model": "m", "content": [{"type": "text", "text": 123}]}}
        self.home.transcript([weird] * 12 + [assistant(NOW - 5, text="好")] * 400)
        data, state = self.run_once()
        self.assertEqual(data["warnings"], [])
        self.assertEqual(list(state["transcripts"].values())[0]["badLines"], 12)  # 對照組：有記到這 12 行，只是佔比很低所以不叫

    # --- 用真實情況測出來的：`claude -p` 這類沒有人坐在前面的 session，跑完就走是常態 ---
    def test_headless_run_that_finishes_is_not_called_crashed_and_not_remembered(self):
        self.home.proc(101, status="busy", entrypoint="sdk-cli")
        row, _, state = self.one()
        self.assertEqual((row["state"], row["headless"]), ("running", True))
        data, state2 = self.run_once(state=state, now=NOW + 5, live=lambda pid: False)
        self.assertEqual(data["sessions"], [])  # 不進「已關閉」、不進急診室
        self.assertEqual(state2["seen"], {})
        self.home.proc(101, status="busy")  # 對照組：你自己開的 session 忙到一半不見，照樣標成當掉
        _, _, state = self.one()
        row = self.one(state=state, now=NOW + 5, live=lambda pid: False)[0]
        self.assertEqual(row["trouble"]["kind"], "crashed")
        self.assertNotIn("headless", row)

    def test_short_lived_headless_run_is_not_drawn_at_all(self):
        self.home.proc(101, status="busy", entrypoint="sdk-cli", startedAt=(NOW - 20) * 1000)
        self.assertEqual(self.run_once()[0]["sessions"], [])
        self.home.proc(101, status="busy", entrypoint="sdk-cli", startedAt=(NOW - 61) * 1000)  # 對照組：開超過一分鐘就畫
        self.assertEqual(self.one()[0]["state"], "running")
        self.home.proc(101, status="busy", startedAt=(NOW - 20) * 1000)  # 對照組：你自己剛開的一定畫
        self.assertEqual(self.one()[0]["state"], "running")

    def test_only_known_headless_kinds_are_treated_quietly(self):
        for entrypoint in (None, "", "claude-vscode", "terminal", 7):
            self.home.proc(101, status="busy", entrypoint=entrypoint, startedAt=(NOW - 20) * 1000)
            row, _, state = self.one()
            self.assertNotIn("headless", row, entrypoint)
            gone = self.one(state=state, now=NOW + 5, live=lambda pid: False)[0]
            self.assertEqual(gone["trouble"]["kind"], "crashed", entrypoint)
        p = self.home.proc(101, entrypoint=None)
        del p["status"]
        with open(os.path.join(self.home.paths["sessions"], "101.json"), "w") as fh:
            json.dump({k: v for k, v in p.items() if k not in ("statusUpdatedAt", "updatedAt")}, fh)
        self.assertEqual(self.one()[0]["state"], "unknown:沒有狀態")  # entrypoint 是空的、狀態也不見：要講出來

    def test_sdk_session_whose_helper_is_writing_counts_as_running(self):
        self.sdk_proc()
        path = self.home.transcript([human("開始", NOW - 900), assistant(NOW - 800, text="派出去了")])
        os.utime(path, (NOW - 800, NOW - 800))
        sub = path[:-6] + "/subagents"
        os.makedirs(sub)
        f = os.path.join(sub, "agent-zz9.jsonl")
        open(f, "w").close()
        os.utime(f, (NOW - 15, NOW - 15))
        self.assertEqual(self.one()[0]["state"], "running")

    # --- 第四輪審查後補的 ---
    def test_headless_file_with_odd_fields_does_not_take_everyone_down(self):
        self.home.proc(101, status="busy")
        for odd in ({"startedAt": "不是數字"}, {"startedAt": None}, {"startedAt": [1]}, {"updatedAt": "x", "statusUpdatedAt": {}, "status": 5}):
            self.home.proc(102, sid=SID2, entrypoint="sdk-cli", tmux="work:@2.%6", **odd)
            data, _ = self.run_once()
            by_id = {s["id"]: s for s in data["sessions"]}
            self.assertEqual(by_id[SID]["state"], "running", odd)  # 正常的那張一定還在
            self.assertNotIn("trouble", by_id[SID], odd)
            if SID2 in by_id and "startedAt" in odd and odd["startedAt"] is not None:
                self.assertEqual(by_id[SID2]["trouble"]["kind"], "unreadable", odd)

    def test_your_own_session_wins_over_a_script_resuming_the_same_one(self):
        self.home.proc(101, status="idle", updatedAt=(NOW - 600) * 1000)
        self.home.proc(102, status="busy", entrypoint="sdk-cli", startedAt=(NOW - 5) * 1000, updatedAt=NOW * 1000)  # 同一個 sessionId
        row, data, state = self.one()
        self.assertEqual((row["state"], len(data["sessions"])), ("idle", 1))
        self.assertNotIn("headless", row)
        self.assertIn(SID, state["seen"])
        os.remove(os.path.join(self.home.paths["sessions"], "101.json"))  # 對照組：只剩腳本那個時，才照無畫面的規則走（未滿一分鐘不畫）
        self.assertEqual([s["state"] for s in self.run_once()[0]["sessions"]], [])

    # --- 第五輪審查後補的：一個怪值不能讓整間辦公室看不到 ---
    def test_absurd_process_files_count_as_unreadable_not_as_a_crash(self):
        self.home.proc(101, status="busy")
        d = self.home.paths["sessions"]
        with open(os.path.join(d, "201.json"), "w") as fh:
            fh.write('{"pid": 1e999, "sessionId": "test-session-cccc"}')
        with open(os.path.join(d, "202.json"), "w") as fh:
            fh.write("[" * 5000 + "]" * 5000)
        with open(os.path.join(d, "203.json"), "w") as fh:
            fh.write('"只是一個字串"')
        row, data, _ = self.one()
        self.assertEqual((row["state"], data["skipped"]), ("running", 3))

    @unittest.skipIf(os.geteuid() == 0, "root 不受檔案權限限制，測不出來")
    def test_sessions_folder_without_read_permission_is_an_error_not_zero(self):
        self.home.proc(101)
        os.chmod(self.home.paths["sessions"], 0o000)
        self.addCleanup(os.chmod, self.home.paths["sessions"], 0o755)
        with self.assertRaises(collect.CollectError):
            self.run_once()

    def test_tmux_lookup_blowing_up_only_costs_clickability(self):
        self.home.proc(101, status="busy")

        def boom():
            raise UnicodeDecodeError("utf-8", b"\xe9", 0, 1, "怪名字")
        data, _ = collect.collect(NOW, cfg(), self.home.paths, None, alive=alive, list_panes=boom)
        self.assertEqual([(s["state"], s["pane"]) for s in data["sessions"]], [("running", "")])
        self.assertFalse(data["sources"]["tmux"])

    # --- 第六輪審查後補的 ---
    def test_absurdly_long_integers_only_affect_their_own_card(self):
        huge = int("9" * 401)
        self.home.proc(101, status="busy")
        for odd in ({"startedAt": huge}, {"statusUpdatedAt": huge}, {"updatedAt": huge}, {"startedAt": huge, "entrypoint": "sdk-cli"}):
            self.home.proc(102, sid=SID2, tmux="work:@2.%6", **odd)
            data, _ = self.run_once()
            by_id = {s["id"]: s for s in data["sessions"]}
            self.assertEqual(by_id[SID]["state"], "running", list(odd))
            self.assertNotIn("trouble", by_id[SID], list(odd))
            self.assertIn(SID2, by_id, list(odd))  # 怪的那張也還在（進急診室或照常畫），不是整輪失敗

    def test_even_when_the_fallback_card_fails_others_survive(self):
        from unittest import mock
        self.home.proc(101, status="busy")
        self.home.proc(102, sid=SID2, status="busy", startedAt="不是數字", tmux="work:@2.%6")
        with mock.patch.object(collect, "_fallback_row", side_effect=RuntimeError("連備用的都壞了")):
            data, state = self.run_once()
        by_id = {s["id"]: s for s in data["sessions"]}
        self.assertEqual(by_id[SID]["state"], "running")
        self.assertEqual(by_id[SID2]["trouble"]["kind"], "unreadable")
        self.assertIn("RuntimeError", by_id[SID2]["trouble"]["text"])
        self.assertIn(SID2, state["seen"])  # 有記住它還活著，下一輪不會被當成已關閉

    def test_absurdly_long_integer_in_a_duplicate_session_file_is_survivable(self):
        # 同一個 sessionId 兩個檔時要比誰新，那個比較在「每個 session 各自的保護」外面
        self.home.proc(101, status="busy", updatedAt=int("9" * 401))
        self.home.proc(102, status="idle")
        data, _ = self.run_once()
        self.assertEqual(len(data["sessions"]), 1)
        self.assertEqual(data["sessions"][0]["state"], "idle")  # 離譜的那個時間當成 0，所以正常的那個檔贏


if __name__ == "__main__":
    unittest.main()
