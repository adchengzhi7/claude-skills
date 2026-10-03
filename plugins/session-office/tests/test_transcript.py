import json
import os
import unittest

from helpers import NOW, FakeHome, assistant, human, iso, tool_result

from office import transcript


class TranscriptTest(unittest.TestCase):
    def setUp(self):
        self.home = FakeHome()
        self.addCleanup(self.home.cleanup)

    def read(self, lines, entry=None, **kw):
        path = self.home.transcript(lines, **kw)
        return transcript.update(entry, path, NOW), path

    def test_human_message_and_report(self):
        e, _ = self.read([human("幫我看首頁", NOW - 100), assistant(NOW - 90, text="  看完了，有三個問題。 ")])
        self.assertEqual(e["lastUser"], "幫我看首頁")
        self.assertEqual(e["turns"], 1)
        self.assertEqual(e["lastReport"], "看完了，有三個問題。")
        self.assertEqual(e["lastOkAt"], NOW - 90)

    def test_tool_result_is_not_a_human_turn(self):
        e, _ = self.read([human("跑測試", NOW - 100), assistant(NOW - 90, tool=("t1", "Bash", {"command": "npm test"})),
                          tool_result("t1", NOW - 80)])
        self.assertEqual(e["turns"], 1)
        self.assertEqual(e["lastUser"], "跑測試")

    def test_slash_command_shows_command_name(self):
        e, _ = self.read([human("<command-name>/clear</command-name><command-args></command-args>", NOW - 10)])
        self.assertEqual(e["lastUser"], "/clear")

    def test_old_format_without_origin(self):
        old = {"type": "user", "timestamp": iso(NOW - 50), "message": {"role": "user", "content": "沒有 origin 的舊格式"}}
        injected = {"type": "user", "timestamp": iso(NOW - 40), "message": {"role": "user", "content": "<task-notification>x</task-notification>"}}
        e, _ = self.read([old, injected])
        self.assertEqual((e["lastUser"], e["turns"]), ("沒有 origin 的舊格式", 1))

    def test_pending_question_then_answered(self):
        ask = assistant(NOW - 30, tool=("t9", "AskUserQuestion", {"questions": [{"question": "要 A 還是 B？"}]}))
        e, path = self.read([human("開始", NOW - 40), ask])
        self.assertEqual(transcript.waiting_on(e), {"name": "AskUserQuestion", "brief": "要 A 還是 B？"})
        self.home.transcript([tool_result("t9", NOW - 5)], append=True)
        e = transcript.update(e, path, NOW)
        self.assertIsNone(transcript.waiting_on(e))

    def test_permission_brief_uses_command(self):
        e, _ = self.read([assistant(NOW - 30, tool=("t2", "Bash", {"command": "rm -rf build", "description": "清掉"}))])
        self.assertEqual(transcript.waiting_on(e), {"name": "Bash", "brief": "rm -rf build"})

    def test_new_human_message_clears_stale_pending(self):
        e, _ = self.read([assistant(NOW - 30, tool=("t2", "Bash", {"command": "sleep 99"})), human("算了，改做別的", NOW - 10)])
        self.assertIsNone(transcript.waiting_on(e))

    def test_big_tool_result_line_still_clears_pending(self):
        big = tool_result("t3", NOW - 5, text="x" * (transcript.BIG_LINE + 10))
        e, _ = self.read([assistant(NOW - 30, tool=("t3", "Read", {"file_path": "/a"})), big])
        self.assertIsNone(transcript.waiting_on(e))

    def test_helpers_out_and_back(self):
        launch = tool_result("t1", NOW - 300, result={"status": "async_launched", "agentId": "abc123"})
        e, path = self.read([assistant(NOW - 310, tool=("t1", "Agent", {"prompt": "查"})), launch])
        self.assertEqual(transcript.helpers_out(e, path, NOW)[0], 1)  # 對照組：派出去還沒回來＝1
        done = {"type": "queue-operation", "operation": "enqueue", "timestamp": iso(NOW - 100), "content": "<task-id>abc123</task-id>"}
        self.home.transcript([done], append=True)
        e = transcript.update(e, path, NOW)
        self.assertEqual(transcript.helpers_out(e, path, NOW)[0], 0)

    def test_queue_remove_line_does_not_count_as_back(self):
        launch = tool_result("t1", NOW - 300, result={"status": "async_launched", "agentId": "abc123"})
        removed = {"type": "queue-operation", "operation": "remove", "timestamp": iso(NOW - 100), "content": "<task-id>abc123</task-id>"}
        e, path = self.read([launch, removed])
        self.assertEqual(transcript.helpers_out(e, path, NOW)[0], 1)

    def test_send_message_redispatches_agent(self):
        launch = tool_result("t1", NOW - 300, result={"status": "async_launched", "agentId": "abc123"})
        done = {"type": "queue-operation", "operation": "enqueue", "timestamp": iso(NOW - 200), "content": "<task-id>abc123</task-id>"}
        again = assistant(NOW - 100, tool=("t5", "SendMessage", {"to": "abc123", "message": "再補一段"}))
        e, path = self.read([launch, done, again])
        self.assertEqual(transcript.helpers_out(e, path, NOW)[0], 1)

    def test_stale_helper_not_counted(self):
        launch = tool_result("t1", NOW - 7 * 3600, result={"status": "async_launched", "agentId": "abc123"})
        e, path = self.read([launch])
        self.assertEqual(transcript.helpers_out(e, path, NOW)[0], 0)

    def test_subagent_file_written_recently_counts(self):
        e, path = self.read([human("開始", NOW - 40)])
        sub = path[:-6] + "/subagents"
        os.makedirs(sub)
        f = os.path.join(sub, "agent-zz9.jsonl")
        open(f, "w").close()
        os.utime(f, (NOW - 30, NOW - 30))
        self.assertEqual(transcript.helpers_out(e, path, NOW)[0], 1)
        os.utime(f, (NOW - 900, NOW - 900))
        self.assertEqual(transcript.helpers_out(e, path, NOW)[0], 0)

    def test_usage_sets_tokens_and_ttl(self):
        u1h = {"input_tokens": 10, "cache_read_input_tokens": 1000, "cache_creation_input_tokens": 90,
               "cache_creation": {"ephemeral_1h_input_tokens": 90}}
        e, path = self.read([assistant(NOW - 50, text="a", usage=u1h)])
        self.assertEqual((e["ctxTokens"], e["ttl"], e["lastCallAt"]), (1100, 3600, NOW - 50))
        u5m = {"input_tokens": 5, "cache_read_input_tokens": 2000, "cache_creation_input_tokens": 5,
               "cache_creation": {"ephemeral_5m_input_tokens": 5}}
        self.home.transcript([assistant(NOW - 10, text="b", usage=u5m)], append=True)
        e = transcript.update(e, path, NOW)
        self.assertEqual((e["ctxTokens"], e["ttl"]), (2010, 300))

    def test_api_error_is_not_a_real_reply(self):
        ok = assistant(NOW - 100, text="正常回覆", usage={"input_tokens": 500})
        err = assistant(NOW - 20, text="API Error: 529 overloaded", model="<synthetic>", usage={"input_tokens": 0}, isApiErrorMessage=True)
        e, _ = self.read([ok, err])
        self.assertEqual(e["lastErrAt"], NOW - 20)
        self.assertIn("529", e["lastErrText"])
        self.assertEqual((e["lastOkAt"], e["ctxTokens"], e["lastReport"]), (NOW - 100, 500, "正常回覆"))

    def test_sidechain_lines_ignored(self):
        side = {**assistant(NOW - 10, text="子 agent 說的話"), "isSidechain": True}
        e, _ = self.read([assistant(NOW - 50, text="主線"), side])
        self.assertEqual(e["lastReport"], "主線")

    def test_ai_title(self):
        e, _ = self.read([{"type": "ai-title", "aiTitle": "整理月結報表"}])
        self.assertEqual(e["title"], "整理月結報表")

    def test_incremental_half_line_waits(self):
        path = self.home.transcript([human("第一句", NOW - 50)])
        e = transcript.update(None, path, NOW)
        half = json.dumps(human("第二句", NOW - 10), ensure_ascii=False)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(half[:20])
        e = transcript.update(e, path, NOW)
        self.assertEqual(e["lastUser"], "第一句")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(half[20:] + "\n")
        e = transcript.update(e, path, NOW)
        self.assertEqual((e["lastUser"], e["turns"]), ("第二句", 2))

    def test_update_does_not_mutate_input(self):
        path = self.home.transcript([assistant(NOW - 30, tool=("t2", "Bash", {"command": "ls"}))])
        e1 = transcript.update(None, path, NOW)
        snapshot = json.dumps(e1, sort_keys=True)
        self.home.transcript([tool_result("t2", NOW - 5), human("下一句", NOW - 1)], append=True)
        transcript.update(e1, path, NOW)
        self.assertEqual(json.dumps(e1, sort_keys=True), snapshot)

    def test_file_replaced_by_smaller_restarts(self):
        path = self.home.transcript([human("很長很長的第一句" * 20, NOW - 50), human("第二句", NOW - 40)])
        e = transcript.update(None, path, NOW)
        self.assertEqual(e["turns"], 2)
        self.home.transcript([human("新的", NOW - 5)])
        e = transcript.update(e, path, NOW)
        self.assertEqual((e["lastUser"], e["turns"]), ("新的", 1))

    def test_missing_file_returns_entry_unchanged(self):
        e = transcript.update(None, os.path.join(self.home.root, "nope.jsonl"), NOW)
        self.assertEqual(e, transcript.new_entry())

    def test_first_read_of_huge_file_only_reads_tail(self):
        old_tail = transcript.FIRST_READ_TAIL
        transcript.FIRST_READ_TAIL = 2000
        self.addCleanup(setattr, transcript, "FIRST_READ_TAIL", old_tail)
        lines = [human("舊的 %d " % i + "x" * 200, NOW - 1000 + i) for i in range(50)] + [human("最後一句", NOW - 1)]
        e, _ = self.read(lines)
        self.assertEqual(e["lastUser"], "最後一句")
        self.assertLess(e["turns"], 51)
        self.assertGreater(e["turns"], 0)

    def test_compact_summary_is_not_a_human_turn(self):
        summary = {**human("（自動壓縮的摘要）", NOW - 10), "isCompactSummary": True}
        del summary["origin"]
        e, _ = self.read([human("真的人打的", NOW - 50), summary])
        self.assertEqual((e["lastUser"], e["turns"]), ("真的人打的", 1))

    def test_agent_file_with_name_suffix_is_not_counted_twice(self):
        launch = tool_result("t1", NOW - 60, result={"status": "async_launched", "agentId": "abc123"})
        e, path = self.read([launch])
        sub = path[:-6] + "/subagents"
        os.makedirs(sub)
        f = os.path.join(sub, "agent-abc123-reviewer.jsonl")
        open(f, "w").close()
        os.utime(f, (NOW - 10, NOW - 10))
        self.assertEqual(transcript.helpers_out(e, path, NOW)[0], 1)

    def test_unopenable_file_returns_entry_instead_of_raising(self):
        path = os.path.join(self.home.root, "is-a-folder.jsonl")
        os.makedirs(path)
        e = transcript.update(None, path, NOW)
        self.assertEqual((e["offset"], e["turns"]), (0, 0))

    def test_lines_with_unexpected_shapes_are_counted_not_fatal(self):
        lines = [{"type": "assistant", "message": "字串"}, {"type": "assistant", "message": {"content": "不是清單", "usage": "不是物件"}},
                 {"type": "assistant", "message": {"model": "m", "content": [{"type": "text", "text": 123}]}}, "[1, 2, 3]", "不是 json",
                 human("最後還是讀得到", NOW - 1)]
        e, path = self.read(lines)
        self.assertEqual((e["lastUser"], e["badLines"]), ("最後還是讀得到", 1))
        self.assertEqual(e["offset"], os.path.getsize(path))


if __name__ == "__main__":
    unittest.main()
