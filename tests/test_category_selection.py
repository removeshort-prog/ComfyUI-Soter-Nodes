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
        self.named_categories = {}
        self.real_named_categories_loader = node_module.load_named_categories
        named_loader_patch = patch.object(node_module, "load_named_categories", return_value=self.named_categories)
        self.named_loader = named_loader_patch.start()
        self.addCleanup(named_loader_patch.stop)

    def rows(self, enabled=()):
        return [{"name": name, "enabled": name in enabled} for name in self.names]

    def process(self, tags, order, **overrides):
        options = {
            "excel_file": str(self.database),
            "category_mapping": repr(self.mapping),
            "new_category_order": json.dumps(order, ensure_ascii=False),
            "validation": True,
            "danbooru_lookup": False,
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

    def test_default_output_is_plain_selected_tags_with_chinese_bundle_keys(self):
        mapping = dict(self.mapping)
        mapping[("镜头", "视线")] = "镜头词"
        mapping[("角色", "眼睛")] = "人物对象词"
        mapping[("角色", "头发")] = "人物对象词"
        rows = [
            {"name": "镜头词", "enabled": True},
            {"name": "表情", "enabled": False},
            {"name": "人物对象词", "enabled": True},
        ]
        response = self.process(
            "red_hair, smile, looking_at_viewer, blue_eyes", rows,
            category_mapping=repr(mapping),
        )
        bundle, text = response["result"]
        self.assertEqual(text, "looking_at_viewer, \nblue_eyes, red_hair, ")
        self.assertEqual(list(bundle), ["镜头词", "人物对象词"])
        self.assertEqual(bundle, {
            "镜头词": "looking_at_viewer, ",
            "人物对象词": "blue_eyes, red_hair, ",
        })
        self.assertEqual(self.preview(response)["表情"], "smile, ")
        for unwanted in ("smile", "镜头词", "人物对象词", "{", "}", "[", "]", "\\u"):
            self.assertNotIn(unwanted, text)
        getter = node_module.DanbooruTagGetterNode()
        self.assertEqual(getter.get_tag(bundle, "镜头词"), ("looking_at_viewer, ",))
        self.assertEqual(getter.get_tag(bundle, "人物对象词"), ("blue_eyes, red_hair, ",))
        self.assertEqual(getter.get_tag(bundle, "表情"), ("",))
        self.assertFalse(self.node.INPUT_TYPES()["optional"]["is_comment"][1]["default"])

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
        self.assertEqual(set(preview), set(self.names) | {"版权", "角色名"})
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

    def test_named_categories_split_mixed_database_and_supplement_absent_names(self):
        with self.database.open("a", encoding="utf-8", newline="") as stream:
            csv.writer(stream).writerows([
                ["sample_series", "二次元角色", ""],
                ["sample_hero", "二次元角色", ""],
            ])
        self.named_categories.update({
            "sample series": "copyright",
            "sample hero": "character",
            "supplemental hero": "character",
        })
        rows = [
            {"name": "角色名", "enabled": True},
            {"name": "版权", "enabled": True},
            {"name": "未归类词", "enabled": True},
        ]
        response = self.process("supplemental_hero, sample_series, smile, sample_hero, unknown_tag", rows)
        self.assertEqual(response["result"], ({
            "角色名": "sample_hero, supplemental_hero, ",
            "版权": "sample_series, ",
            "未归类词": "unknown_tag, ",
        }, "sample_hero, supplemental_hero, \nsample_series, \nunknown_tag, "))
        self.assertEqual(self.preview(response)["表情"], "smile, ")

    def test_old_structured_rows_preview_new_categories_without_enabling_them(self):
        self.named_categories.update({"sample series": "copyright", "sample hero": "character"})
        response = self.process("sample_series, sample_hero, unknown_tag", self.rows(["未归类词"]))
        self.assertEqual(response["result"], ({"未归类词": "unknown_tag, "}, "unknown_tag, "))
        preview = self.preview(response)
        self.assertEqual(preview["版权"], "sample_series, ")
        self.assertEqual(preview["角色名"], "sample_hero, ")

    def test_explicit_database_mapping_wins_over_named_category_metadata(self):
        self.named_categories["red hair"] = "character"
        response = self.process("red_hair", self.rows(["外观"]))
        self.assertEqual(response["result"], ({"外观": "red_hair, "}, "red_hair, "))
        self.assertEqual(self.preview(response)["角色名"], "")

    def test_custom_named_category_mapping_controls_output_names_and_order(self):
        self.named_categories.update({"sample series": "copyright", "sample hero": "character"})
        mapping = dict(self.mapping)
        mapping[("版权", "作品")] = "作品清单"
        mapping[("角色", "角色名")] = "人物清单"
        rows = [{"name": "人物清单", "enabled": True}, {"name": "作品清单", "enabled": True}]
        response = self.process("sample_series, sample_hero", rows, category_mapping=repr(mapping))
        self.assertEqual(response["result"], ({
            "人物清单": "sample_hero, ", "作品清单": "sample_series, ",
        }, "sample_hero, \nsample_series, "))
        self.assertNotIn("版权", self.preview(response))
        self.assertNotIn("角色名", self.preview(response))

    def test_new_node_defaults_classify_real_snapshot_names_without_extra_csv_rows(self):
        self.named_loader.side_effect = self.real_named_categories_loader
        with contextlib.redirect_stdout(io.StringIO()):
            response = self.node.process(
                "suzuran_(arknights), arknights, vulpisfoglia_(arknights)",
                excel_file=str(self.database), danbooru_lookup=False,
            )
        bundle, text = response["result"]
        self.assertEqual(list(bundle)[:2], ["版权", "角色名"])
        self.assertEqual(len(bundle), 14)
        self.assertEqual(bundle["版权"], "arknights, ")
        self.assertEqual(bundle["角色名"], "suzuran_(arknights), vulpisfoglia_(arknights), ")
        self.assertEqual(text, "arknights, \nsuzuran_(arknights), vulpisfoglia_(arknights), ")
        self.assertEqual(self.preview(response)["未归类词"], "")
        self.assertTrue(self.node.INPUT_TYPES()["optional"]["danbooru_lookup"][1]["default"])

    def test_gallery_space_and_escaped_parentheses_are_matched_without_rewriting_tags(self):
        self.named_categories.update({"sample series": "copyright", "sample hero (series)": "character"})
        rows = [{"name": "版权", "enabled": True}, {"name": "角色名", "enabled": True}]
        response = self.process(r"sample hero \(series\), sample series", rows)
        self.assertEqual(response["result"], ({
            "版权": "sample series, ", "角色名": r"sample hero \(series\), ",
        }, "sample series, \n" + r"sample hero \(series\), "))

    def test_live_lookup_only_queries_unresolved_unfiltered_names(self):
        self.named_categories["offline hero"] = "character"
        rows = [
            {"name": "版权", "enabled": True},
            {"name": "角色名", "enabled": True},
            {"name": "未归类词", "enabled": True},
        ]
        with patch.object(node_module, "lookup_named_categories", return_value={
            "new series": "copyright", "new hero (series)": "character",
        }) as lookup:
            response = self.process(
                r"new_series, red_hair, offline_hero, blocked_tag, skip_censor, new hero \(series\), unknown_tag, new_series",
                rows, danbooru_lookup=True, deduplicate_tags=True,
                tag_blacklist="blocked_tag", regex_blacklist="censor",
            )
        self.assertEqual(lookup.call_count, 1)
        self.assertEqual(set(lookup.call_args.args[0]), {"new series", "new hero (series)", "unknown tag"})
        self.assertEqual(response["result"], ({
            "版权": "new_series, ",
            "角色名": r"offline_hero, new hero \(series\), ",
            "未归类词": "unknown_tag, ",
        }, "new_series, \noffline_hero, " + "new hero \\(series\\), \nunknown_tag, "))
        self.assertEqual(self.preview(response)["外观"], "red_hair, ")

    def test_live_classified_names_in_disabled_new_categories_do_not_leak_into_default(self):
        with patch.object(node_module, "lookup_named_categories", return_value={
            "new series": "copyright", "new hero": "character",
        }):
            response = self.process(
                "new_series, new_hero, unknown_tag", self.rows(["未归类词"]), danbooru_lookup=True,
            )
        self.assertEqual(response["result"], ({"未归类词": "unknown_tag, "}, "unknown_tag, "))
        preview = self.preview(response)
        self.assertEqual(preview["版权"], "new_series, ")
        self.assertEqual(preview["角色名"], "new_hero, ")

    def test_live_classification_of_existing_unmapped_csv_tag_does_not_poison_offline_cache(self):
        rows = [{"name": "角色名", "enabled": True}, {"name": "未归类词", "enabled": True}]
        with patch.object(node_module, "lookup_named_categories", return_value={"fallback known": "character"}):
            online = self.process("fallback_known", rows, danbooru_lookup=True)
        self.assertEqual(online["result"], ({"角色名": "fallback_known, ", "未归类词": ""}, "fallback_known, "))
        with patch.object(node_module, "lookup_named_categories") as lookup:
            offline = self.process("fallback_known", rows)
        lookup.assert_not_called()
        self.assertEqual(offline["result"], ({"角色名": "", "未归类词": "fallback_known, "}, "fallback_known, "))

    def test_interrogator_output_uses_offline_and_live_categories_without_gallery(self):
        self.named_categories.update({"arknights": "copyright", "known character": "character"})
        prompt = {
            "10": {"class_type": "WD14Tagger", "inputs": {}},
            "20": {"class_type": "DanbooruTagSorterNode", "inputs": {"tags": ["10", 0]}},
        }
        rows = [{"name": name, "enabled": True} for name in ["版权", "角色名", "外观"]]
        with patch.object(node_module, "lookup_named_categories", return_value={"new character": "character"}) as lookup:
            response = self.process("blue_eyes, arknights, known_character, new_character", rows,
                                    prompt=prompt, unique_id="20", danbooru_lookup=True)
        lookup.assert_called_once_with(["new character"])
        self.assertEqual(response["result"], ({
            "版权": "arknights, ",
            "角色名": "known_character, new_character, ",
            "外观": "blue_eyes, ",
        }, "arknights, \nknown_character, new_character, \nblue_eyes, "))

    def test_gallery_hidden_metadata_classifies_current_tags_without_network(self):
        tags = r"arknights, suzuran_\(arknights\), new_prop, known_artist, width_1024"
        prompt = {"7": {"class_type": "DanbooruTagSorterNode", "inputs": {"tags": ["3", 1]}}}
        rows = [
            {"name": "角色名", "enabled": True},
            {"name": "版权", "enabled": True},
            {"name": "未归类词", "enabled": True},
        ]
        with patch.object(node_module, "get_gallery_categories", return_value={
            "arknights": "copyright", "suzuran (arknights)": "character",
            "new prop": "general", "known artist": "artist", "width 1024": "meta",
        }) as gallery, patch.object(node_module, "lookup_named_categories") as lookup:
            response = self.process(tags, rows, prompt=prompt, unique_id="7", danbooru_lookup=True)
        gallery.assert_called_once_with(prompt, "7", tags)
        lookup.assert_not_called()
        self.assertEqual(response["result"], ({
            "角色名": r"suzuran_\(arknights\), ",
            "版权": "arknights, ",
            "未归类词": "new_prop, known_artist, width_1024, ",
        }, "suzuran_\\(arknights\\), \narknights, \nnew_prop, known_artist, width_1024, "))
        self.assertEqual(self.node.INPUT_TYPES()["hidden"], {"prompt": "PROMPT", "unique_id": "UNIQUE_ID"})

    def test_gallery_categories_override_offline_metadata_without_contaminating_other_images(self):
        self.named_categories["fallback known"] = "character"
        rows = [
            {"name": "版权", "enabled": True},
            {"name": "角色名", "enabled": True},
            {"name": "未归类词", "enabled": True},
        ]
        with patch.object(node_module, "get_gallery_categories", side_effect=[
            {"fallback known": "copyright"}, {"fallback known": "general"}, {},
        ]), patch.object(node_module, "lookup_named_categories") as lookup, \
                patch.object(node_module.pd, "read_csv", wraps=node_module.pd.read_csv) as read_csv:
            copyright_image = self.process("fallback_known", rows, danbooru_lookup=True)
            general_image = self.process("fallback_known", rows, danbooru_lookup=True)
            plain_input = self.process("fallback_known", rows, danbooru_lookup=True)
        lookup.assert_not_called()
        self.assertEqual(read_csv.call_count, 1)
        self.assertEqual(copyright_image["result"][0], {"版权": "fallback_known, ", "角色名": "", "未归类词": ""})
        self.assertEqual(general_image["result"][0], {"版权": "", "角色名": "", "未归类词": "fallback_known, "})
        self.assertEqual(plain_input["result"][0], {"版权": "", "角色名": "fallback_known, ", "未归类词": ""})

    def test_gallery_metadata_respects_user_database_and_named_category_mappings(self):
        self.named_categories["red hair"] = "copyright"
        mapping = dict(self.mapping)
        mapping[("角色", "角色名")] = "我的角色"
        rows = [{"name": "我的角色", "enabled": True}, {"name": "外观", "enabled": True}]
        with patch.object(node_module, "get_gallery_categories", return_value={
            "red hair": "character", "new hero": "character",
        }), patch.object(node_module, "lookup_named_categories") as lookup:
            response = self.process("red_hair, new_hero", rows, category_mapping=repr(mapping), danbooru_lookup=True)
        lookup.assert_not_called()
        self.assertEqual(response["result"], ({
            "我的角色": "new_hero, ", "外观": "red_hair, ",
        }, "new_hero, \nred_hair, "))

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

    def test_legacy_workflow_with_explicit_comments_preserves_category_labels(self):
        response = self.process("smile, red_hair", self.names, is_comment=True)
        self.assertIsInstance(response, tuple)
        self.assertEqual(response[1], "外观:\nred_hair, \n表情:\nsmile, ")

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
