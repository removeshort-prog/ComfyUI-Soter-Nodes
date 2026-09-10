import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import danbooru_lookup as lookup


class LookupTests(unittest.TestCase):
    def setUp(self):
        lookup.clear_lookup_cache()
        self.now = 100.0
        self.sleep_calls = []
        self.patchers = [
            patch.object(lookup.time, "monotonic", side_effect=lambda: self.now),
            patch.object(lookup.time, "sleep", side_effect=self.sleep),
            patch.object(lookup, "_next_request_at", 0.0),
            patch.object(lookup, "_warned", False),
            patch.object(lookup, "urlopen"),
            patch.object(lookup._logger, "warning"),
        ]
        mocks = [patcher.start() for patcher in self.patchers]
        self.opener = mocks[4]
        self.warning = mocks[5]
        for patcher in self.patchers:
            self.addCleanup(patcher.stop)
        self.addCleanup(lookup.clear_lookup_cache)

    def sleep(self, duration):
        self.sleep_calls.append(duration)
        self.now += duration

    def respond(self, data):
        self.opener.return_value = io.BytesIO(json.dumps(data).encode())

    def test_exact_query_normalization_and_categories(self):
        self.respond([
            {"name": "arknights", "category": 3},
            {"name": "suzuran_(arknights)", "category": 4},
            {"name": "character_name", "category": 0},
        ])
        result = lookup.lookup_named_categories([
            "Arknights", "suzuran \\(arknights\\)", "suzuran_(arknights)", "character name",
        ])
        self.assertEqual(result, {"arknights": "copyright", "suzuran (arknights)": "character"})
        request = self.opener.call_args.args[0]
        params = parse_qs(urlparse(request.full_url).query)
        self.assertEqual(params["search[name_comma]"], ["arknights,suzuran_(arknights),character_name"])
        self.assertEqual(params["only"], ["name,category"])
        self.assertEqual(params["limit"], ["100"])
        self.assertEqual(request.get_header("User-agent"), lookup.USER_AGENT)
        self.assertEqual(self.opener.call_args.kwargs["timeout"], 5)

    def test_positive_other_and_absent_caches_have_distinct_ttls(self):
        self.respond([{"name": "arknights", "category": 3}, {"name": "smile", "category": 0}])
        names = ["arknights", "smile", "absent"]
        expected = {"arknights": "copyright"}
        self.assertEqual(lookup.lookup_named_categories(names), expected)
        self.assertEqual(lookup.lookup_named_categories(names), expected)
        self.assertEqual(self.opener.call_count, 1)
        self.now += lookup.OTHER_TTL + 1
        self.respond([])
        self.assertEqual(lookup.lookup_named_categories(names), expected)
        params = parse_qs(urlparse(self.opener.call_args.args[0].full_url).query)
        self.assertEqual(params["search[name_comma]"], ["smile,absent"])
        self.now += lookup.NAMED_TTL
        self.respond([])
        self.assertEqual(lookup.lookup_named_categories(names), {})
        self.assertEqual(self.opener.call_count, 3)

    def test_batching_limits_and_rate_across_calls(self):
        def reply(request, timeout):
            names = parse_qs(urlparse(request.full_url).query)["search[name_comma]"][0].split(",")
            self.assertLessEqual(len(names), 100)
            return io.BytesIO(json.dumps([{"name": name, "category": 4} for name in names]).encode())
        self.opener.side_effect = reply
        self.assertEqual(len(lookup.lookup_named_categories([f"name_{i}" for i in range(205)])), 205)
        lookup.lookup_named_categories(["one_more"])
        self.assertEqual(self.opener.call_count, 4)
        self.assertEqual(self.sleep_calls, [1.0, 1.0, 1.0])

    def test_failure_stops_remaining_batches_without_poisoning_cache(self):
        names = [f"name_{i}" for i in range(205)]
        good = io.BytesIO(json.dumps([{"name": "name_0", "category": 4}]).encode())
        self.opener.side_effect = [good, TimeoutError("offline")]
        self.assertEqual(lookup.lookup_named_categories(names), {"name 0": "character"})
        self.assertEqual(self.opener.call_count, 2)
        self.opener.side_effect = None
        self.respond([{"name": "name_100", "category": 3}])
        self.assertEqual(lookup.lookup_named_categories(["name_100"]), {"name 100": "copyright"})
        self.assertEqual(self.opener.call_count, 3)
        self.warning.assert_called_once()

    def test_repeated_failures_warn_once_and_are_retried(self):
        self.opener.side_effect = OSError("offline")
        self.assertEqual(lookup.lookup_named_categories(["arknights"]), {})
        self.assertEqual(lookup.lookup_named_categories(["arknights"]), {})
        self.assertEqual(self.opener.call_count, 2)
        self.warning.assert_called_once()

    def test_invalid_responses_are_not_negative_cached(self):
        invalid_payloads = [
            {"error": "blocked"},
            [None],
            [{"name": "arknights", "category": "3"}],
            [{"name": "arknights", "category": True}],
            [{"name": "arknights", "category": 3}, {"name": "arknights", "category": 4}],
            [{"name": "not_requested", "category": 3}],
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                lookup.clear_lookup_cache()
                before = self.opener.call_count
                self.respond(payload)
                self.assertEqual(lookup.lookup_named_categories(["arknights"]), {})
                self.respond([{"name": "arknights", "category": 3}])
                self.assertEqual(lookup.lookup_named_categories(["arknights"]), {"arknights": "copyright"})
                self.assertEqual(self.opener.call_count, before + 2)

    def test_invalid_json_and_oversized_response_are_retried(self):
        for raw in [b"not JSON", b" " * (lookup.MAX_RESPONSE_BYTES + 1)]:
            with self.subTest(length=len(raw)):
                lookup.clear_lookup_cache()
                self.opener.return_value = io.BytesIO(raw)
                self.assertEqual(lookup.lookup_named_categories(["arknights"]), {})
                self.respond([{"name": "arknights", "category": 3}])
                self.assertEqual(lookup.lookup_named_categories(["arknights"]), {"arknights": "copyright"})

    def test_clear_cache_forces_refresh_but_keeps_rate_limit(self):
        self.respond([{"name": "arknights", "category": 3}])
        lookup.lookup_named_categories(["arknights"])
        lookup.clear_lookup_cache()
        self.respond([])
        self.assertEqual(lookup.lookup_named_categories(["arknights"]), {})
        self.assertEqual(self.opener.call_count, 2)
        self.assertEqual(self.sleep_calls, [1.0])

    def test_empty_or_invalid_names_do_not_request(self):
        self.assertEqual(lookup.lookup_named_categories(["", "   ", None, "two,names"]), {})
        self.opener.assert_not_called()

    def test_significant_repeated_underscores_are_preserved(self):
        self.respond([{"name": "foo__bar", "category": 4}])
        self.assertEqual(lookup.lookup_named_categories(["foo__bar"]), {"foo  bar": "character"})
        params = parse_qs(urlparse(self.opener.call_args.args[0].full_url).query)
        self.assertEqual(params["search[name_comma]"], ["foo__bar"])


if __name__ == "__main__":
    unittest.main()
