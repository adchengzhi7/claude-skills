import json
import os
import tempfile
import unittest

import helpers  # noqa: F401  （把套件路徑加進來）

from office import config


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "config.json")

    def write(self, obj):
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write(obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False))

    def test_no_file_means_defaults(self):
        self.assertEqual(config.load(self.path), config.DEFAULTS)

    def test_valid_file_is_merged_over_defaults(self):
        self.write({"groups": [{"name": "客戶A", "color": "#d9480f", "match": "client-a|客戶A"}], "mark": {"label": "重要", "match": "急"},
                    "ballPhrases": ["球在你這裡"], "contextWindow": 200000})
        c = config.load(self.path)
        self.assertEqual((c["groups"][0]["name"], c["mark"]["label"], c["port"], c["contextWindow"]), ("客戶A", "重要", 8765, 200000))

    def assertBad(self, obj, word):
        self.write(obj)
        with self.assertRaises(config.ConfigError) as cm:
            config.load(self.path)
        self.assertIn(word, str(cm.exception))

    def test_broken_json_is_an_error_not_defaults(self):
        self.assertBad("{ groups: ", "JSON")

    def test_unknown_key(self):
        self.assertBad({"gruops": []}, "gruops")

    def test_bad_regex(self):
        self.assertBad({"groups": [{"name": "a", "color": "#fff", "match": "("}]}, "正規表示式")

    def test_bad_color(self):
        self.assertBad({"groups": [{"name": "a", "color": "red; background:url(x)", "match": "a"}]}, "color")

    def test_bad_port_and_theme_and_window(self):
        self.assertBad({"port": 80}, "port")
        self.assertBad({"port": True}, "port")
        self.assertBad({"theme": "../x"}, "theme")
        self.assertBad({"contextWindow": "big"}, "contextWindow")

    def test_bad_mark_and_phrases(self):
        self.assertBad({"mark": {"label": "", "match": "a"}}, "label")
        self.assertBad({"ballPhrases": ["ok", 3]}, "ballPhrases")

    def test_public_part_hides_the_rest(self):
        self.assertEqual(sorted(config.public_part(config.load(self.path))), ["ballPhrases", "groups", "mark"])


if __name__ == "__main__":
    unittest.main()
