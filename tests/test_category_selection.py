"""Exercise the node API with a real CSV database, without a ComfyUI server.

Run with ``python -m unittest discover -s tests -v``. pandas must be installed.
"""

import contextlib
import csv
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


NODE_PATH = Path(__file__).resolve().parents[1] / "node.py"
spec = importlib.util.spec_from_file_location("danbooru_selection_test_node", NODE_PATH)
node_module = importlib.util.module_from_spec(spec)
with contextlib.redirect_stdout(io.StringIO()):
    spec.loader.exec_module(node_module)


class CategorySelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = Path(self.temp_dir.name) / "标签.csv"
        with self.database.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["english", "category", "subcategory"])
            writer.writerows([
                ["smile", "角色", "表情"],
                ["blue_eyes", "角色", "眼睛"],
                ["red_hair", "角色", "头发"],
                ["looking_at_viewer", "镜头", "视线"],
                ["landscape", "场景", "风景"],
                ["fallback_known", "未映射", "未映射"],
            ])
        self.mapping = {
            ("角色", "表情"): "表情",
            ("角色", "眼睛"): "外观",
            ("角色", "头发"): "外观",
            ("镜头", "视线"): "镜头",
            ("场景", "风景"): "背景",
            ("风格", "画师"): "空分类",
        }
        self.names = ["外观", "表情", "镜头", "背景", "空分类", "未归类词"]
        self.node = node_module.DanbooruTagSorterNode()
        node_module._tag_cache.clear()

    def rows(self, enabled=()):
        return [{"name": name, "enabled": name in enabled} for name in self.names]

    def process(self, tags, order, **overrides):
        options = {
            "excel_file": str(self.database),
            "category_mapping": repr(self.mapping),
            "new_category_order": json.dumps(order, ensure_ascii=False),
            "validation": True,
            "is_comment": False,
        }
        options.update(overrides)
        with contextlib.redirect_stdout(io.StringIO()):
            return self.node.process(tags, **options)

    def preview(self, response):
        self.assertIsInstance(response, dict)
        self.assertEqual(set(response), {"ui", "result"})
        previews = response["ui"]["category_preview"]
        self.assertEqual(len(previews), 1)
        for item in previews[0]:
            self.assertEqual(set(item), {"name", "tags"})
            self.assertIsInstance(item["tags"], str)
        return {item["name"]: item["tags"] for item in previews[0]}

    def test_selected_bundle_and_text_follow_row_order_including_default(self):
        rows = [
            {"name": "镜头", "enabled": True},
            {"name": "未归类词", "enabled": True},
            {"name": "外观", "enabled": True},
            {"name": "表情", "enabled": False},
        ]
        response = self.process("red_hair, unknown_tag, smile, looking_at_viewer, blue_eyes", rows)
        bundle, text = response["result"]
        self.assertEqual(list(bundle), ["镜头", "未归类词", "外观"])
        self.assertEqual(bundle, {
            "镜头": "looking_at_viewer, ",
            "未归类词": "unknown_tag, ",
            "外观": "blue_eyes, red_hair, ",
        })
        self.assertEqual(text, "looking_at_viewer, \nunknown_tag, \nblue_eyes, red_hair, ")

    def test_disabled_category_tags_do_not_leak_into_default(self):
        response = self.process("smile, blue_eyes, unknown_tag", self.rows(["未归类词"]))
        self.assertEqual(response["result"], ({"未归类词": "unknown_tag, "}, "unknown_tag, "))
        preview = self.preview(response)
        self.assertEqual(preview["表情"], "smile, ")
        self.assertEqual(preview["外观"], "blue_eyes, ")

    def test_preview_includes_empty_disabled_and_unlisted_mapped_categories(self):
        response = self.process("smile, blue_eyes", [{"name": "外观", "enabled": True}])
        self.assertEqual(response["result"], ({"外观": "blue_eyes, "}, "blue_eyes, "))
        preview = self.preview(response)
        self.assertEqual(set(preview), set(self.names))
        self.assertEqual(preview["表情"], "smile, ")
        self.assertEqual(preview["空分类"], "")
        self.assertEqual(preview["未归类词"], "")

    def test_all_disabled_outputs_are_empty_while_preview_still_has_tags(self):
        response = self.process("smile, red_hair, unknown_tag", self.rows())
        self.assertEqual(response["result"], ({}, ""))
        preview = self.preview(response)
        self.assertEqual(preview["表情"], "smile, ")
        self.assertEqual(preview["未归类词"], "unknown_tag, ")

    def test_enabled_empty_category_remains_in_bundle(self):
        response = self.process("", self.rows(["空分类", "外观"]))
        self.assertEqual(response["result"], ({"外观": "", "空分类": ""}, ""))
        self.assertTrue(all(tags == "" for tags in self.preview(response).values()))

    def test_comments_follow_selected_order_and_skip_empty_groups(self):
        rows = [
            {"name": "空分类", "enabled": True},
            {"name": "未归类词", "enabled": True},
            {"name": "外观", "enabled": True},
        ]
        response = self.process("red_hair, unknown_tag", rows, is_comment=True)
        self.assertEqual(response["result"][1], "未归类词:\nunknown_tag, \n外观:\nred_hair, ")

    def test_getter_receives_plain_dict_and_disabled_categories_return_empty(self):
        response = self.process("smile, red_hair", self.rows(["外观"]))
        bundle, _ = response["result"]
        getter = node_module.DanbooruTagGetterNode()
        self.assertEqual(getter.get_tag(bundle, " 外观 "), ("red_hair, ",))
        self.assertEqual(getter.get_tag(bundle, "表情"), ("",))
        self.assertEqual(getter.get_tag({}, "外观"), ("",))

    def test_blacklists_and_deduplication_apply_to_output_and_preview(self):
        response = self.process(
            "red_hair, RED_HAIR, blue_eyes, smile, noisy_censor, keep_me",
            self.rows(self.names), deduplicate_tags=True,
            tag_blacklist="blue_eyes", regex_blacklist="censor",
        )
        bundle, text = response["result"]
        self.assertEqual(bundle["外观"], "red_hair, ")
        self.assertEqual(bundle["未归类词"], "keep_me, ")
        self.assertEqual(self.preview(response)["外观"], "red_hair, ")
        for removed in ("RED_HAIR", "blue_eyes", "noisy_censor"):
            self.assertNotIn(removed, text)
            self.assertNotIn(removed, "".join(self.preview(response).values()))

    def test_deduplication_can_be_disabled(self):
        response = self.process("red_hair, red_hair", self.rows(["外观"]), deduplicate_tags=False)
        self.assertEqual(response["result"][0]["外观"], "red_hair, red_hair, ")

    def test_reordering_and_toggling_reuse_database_without_stale_outputs(self):
        with patch.object(node_module.pd, "read_csv", wraps=node_module.pd.read_csv) as read_csv:
            original = self.process("red_hair, smile", self.rows(self.names))
            reordered = self.process("red_hair, smile", list(reversed(self.rows(self.names))))
            toggled = self.process("red_hair, smile", self.rows(["表情"]))
        self.assertEqual(read_csv.call_count, 1)
        self.assertEqual(original["result"][1], "red_hair, \nsmile, ")
        self.assertEqual(reordered["result"][1], "smile, \nred_hair, ")
        self.assertEqual(toggled["result"], ({"表情": "smile, "}, "smile, "))
        self.assertEqual(self.preview(toggled)["外观"], "red_hair, ")

    def test_force_reload_and_mapping_changes_still_refresh_cached_database(self):
        with patch.object(node_module.pd, "read_csv", wraps=node_module.pd.read_csv) as read_csv:
            self.process("red_hair", self.rows(self.names))
            self.process("red_hair", self.rows(self.names), force_reload=True)
            self.assertEqual(read_csv.call_count, 2)
            mapping = dict(self.mapping)
            mapping[("角色", "头发")] = "表情"
            changed = self.process("red_hair", self.rows(["表情"]), category_mapping=repr(mapping))
        self.assertEqual(read_csv.call_count, 3)
        self.assertEqual(changed["result"], ({"表情": "red_hair, "}, "red_hair, "))

    def test_custom_unicode_categories_and_mapping_to_default(self):
        mapping = dict(self.mapping)
        mapping[("角色", "表情")] = "自定义·情绪 🌸"
        mapping[("未映射", "未映射")] = "其他 🧩"
        rows = [
            {"name": "其他 🧩", "enabled": True},
            {"name": "自定义·情绪 🌸", "enabled": True},
        ]
        response = self.process(
            "unknown_一, smile, fallback_known, unknown_二", rows,
            category_mapping=repr(mapping), default_category="其他 🧩",
        )
        bundle, text = response["result"]
        self.assertEqual(list(bundle), ["其他 🧩", "自定义·情绪 🌸"])
        self.assertEqual(bundle["其他 🧩"], "fallback_known, unknown_一, unknown_二, ")
        self.assertEqual(bundle["自定义·情绪 🌸"], "smile, ")
        self.assertEqual(text, "fallback_known, unknown_一, unknown_二, \nsmile, ")

    def test_duplicate_categories_keep_first_choice_without_duplicating_tags(self):
        rows = [
            {"name": "外观", "enabled": False},
            {"name": "外观", "enabled": True},
            {"name": "表情", "enabled": True},
            {"name": "表情", "enabled": False},
        ]
        response = self.process("blue_eyes, smile", rows)
        self.assertEqual(response["result"], ({"表情": "smile, "}, "smile, "))
        names = [row["name"] for row in response["ui"]["category_preview"][0]]
        self.assertEqual(names.count("外观"), 1)
        self.assertEqual(names.count("表情"), 1)

    def test_direct_python_rows_and_omitted_enabled_are_supported(self):
        response = self.process("smile", [], new_category_order=[{"name": "表情"}])
        self.assertEqual(response["result"], ({"表情": "smile, "}, "smile, "))

    def test_invalid_structured_records_raise_instead_of_silently_enabling(self):
        invalid_orders = [
            [{"name": "外观", "enabled": "false"}],
            [{"name": "外观", "enabled": 0}],
            [{"name": "外观", "enabled": None}],
            [{"name": "", "enabled": True}],
            [{"name": "   ", "enabled": True}],
            [{"name": 123, "enabled": True}],
            [{"enabled": True}],
            [{"name": "外观", "enabled": True}, "表情"],
        ]
        for order in invalid_orders:
            with self.subTest(order=order), self.assertRaises(ValueError):
                self.process("red_hair", order, validation=False)

    def test_legacy_string_list_keeps_tuple_and_omitted_category_fallback(self):
        response = self.process("smile, blue_eyes, unknown_tag", ["外观"], validation=False)
        self.assertIsInstance(response, tuple)
        self.assertEqual(response, (
            {"外观": "blue_eyes, ", "未归类词": "smile, unknown_tag, "},
            "blue_eyes, \nsmile, unknown_tag, ",
        ))

    def test_legacy_python_literal_and_direct_list_remain_supported(self):
        for order in (repr(self.names), self.names):
            with self.subTest(order=order):
                response = self.process("red_hair, blue_eyes", [], new_category_order=order)
                self.assertIsInstance(response, tuple)
                self.assertEqual(response[0]["外观"], "blue_eyes, red_hair, ")

    def test_legacy_validation_still_rejects_missing_mapping_categories(self):
        with self.assertRaises(ValueError):
            self.process("red_hair", ["外观"])

    def test_legacy_empty_order_keeps_unknown_fallback(self):
        response = self.process("smile, unknown_tag", [], validation=False)
        self.assertEqual(response, (
            {"未归类词": "smile, unknown_tag, "},
            "smile, unknown_tag, ",
        ))


if __name__ == "__main__":
    unittest.main()
