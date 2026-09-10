import copy
import json
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gallery_metadata import get_gallery_categories


def workflow(selections, options=None):
    payload = {"version": 1, "selections": selections}
    if options is not None:
        payload["prompt"] = options
    return {
        "10": {"class_type": "BooruGalleryNode", "inputs": {"gallery_payload": json.dumps(payload)}},
        "20": {"class_type": "DanbooruTagSorterNode", "inputs": {"tags": ["10", 1]}},
    }


class GalleryMetadataTests(unittest.TestCase):
    def test_all_five_categories_and_gallery_fixed_order(self):
        groups = {"artist": ["creator"], "copyright": ["arknights"], "character": ["suzuran_(arknights)"],
                  "general": ["smile"], "meta": ["highres"]}
        graph = workflow([{"originalTags": groups}], {"categories": ["meta", "general", "character", "copyright", "artist"]})
        self.assertEqual(get_gallery_categories(graph, "20", "creator, arknights, suzuran_(arknights), smile, highres"), {
            "creator": "artist", "arknights": "copyright", "suzuran (arknights)": "character",
            "smile": "general", "highres": "meta",
        })

    def test_edited_groups_take_precedence(self):
        graph = workflow([{"originalTags": {"character": ["old_character"]},
                           "editedTags": {"character": ["new_character"]}}])
        self.assertEqual(get_gallery_categories(graph, 20, "new_character"), {"new character": "character"})
        self.assertEqual(get_gallery_categories(graph, 20, "old_character"), {})

    def test_empty_edited_groups_do_not_restore_original(self):
        graph = workflow([{"originalTags": {"character": ["old_character"]}, "editedTags": {}}])
        self.assertEqual(get_gallery_categories(graph, "20", ""), {})
        self.assertEqual(get_gallery_categories(graph, "20", "old_character"), {})

    def test_null_and_non_object_edits_use_original(self):
        for edited in [None, [], "invalid"]:
            with self.subTest(edited=edited):
                graph = workflow([{"originalTags": {"copyright": ["arknights"]}, "editedTags": edited}])
                self.assertEqual(get_gallery_categories(graph, "20", "arknights"), {"arknights": "copyright"})

    def test_multi_image_metadata_is_not_merged(self):
        graph = workflow([
            {"originalTags": {"copyright": ["first_series"], "character": ["first_person"]}},
            {"originalTags": {"copyright": ["second_series"], "character": ["second_person"]}},
        ])
        self.assertEqual(get_gallery_categories(graph, "20", "second_series, second_person"), {
            "second series": "copyright", "second person": "character",
        })
        self.assertEqual(get_gallery_categories(graph, "20", "first_person, second_person"), {})

    def test_exclusions_output_filters_and_disabled_categories(self):
        groups = {"copyright": ["arknights"], "character": ["suzuran_(arknights)", "vulpisfoglia_(arknights)"],
                  "general": ["smile", "hat"], "artist": ["creator"]}
        options = {"categories": ["copyright", "character", "general"],
                   "excludedTags": ["suzuran_(arknights)"], "outputFilterTags": ["hat"]}
        graph = workflow([{"originalTags": groups}], options)
        self.assertEqual(get_gallery_categories(graph, "20", "arknights, vulpisfoglia_(arknights), smile"), {
            "arknights": "copyright", "vulpisfoglia (arknights)": "character", "smile": "general",
        })
        self.assertEqual(get_gallery_categories(graph, "20", "arknights, suzuran_(arknights), vulpisfoglia_(arknights), smile"), {})

    def test_format_options_and_normalized_input(self):
        graph = workflow([{"originalTags": {"character": ["suzuran_(arknights)"], "general": ["blue_eyes"]}}],
                         {"replaceUnderscores": True, "escapeParentheses": True})
        expected = {"suzuran (arknights)": "character", "blue eyes": "general"}
        self.assertEqual(get_gallery_categories(graph, "20", "suzuran \\(arknights\\), blue eyes"), expected)
        self.assertEqual(get_gallery_categories(graph, "20", "SUZURAN_(ARKNIGHTS), blue_eyes, "), expected)

    def test_duplicate_raw_tags_use_gallery_first_enabled_category(self):
        graph = workflow([{"originalTags": {"copyright": ["shared", "shared"], "character": ["shared", "person"]}}])
        self.assertEqual(get_gallery_categories(graph, "20", "shared, person"), {"shared": "copyright", "person": "character"})

    def test_identical_prompt_conflicts_fall_back_per_name(self):
        graph = workflow([
            {"originalTags": {"copyright": ["shared"], "general": ["smile"]}},
            {"originalTags": {"character": ["shared"], "general": ["smile"]}},
        ])
        self.assertEqual(get_gallery_categories(graph, "20", "shared, smile"), {"smile": "general"})

    def test_normalization_collision_is_not_assigned_arbitrary_category(self):
        graph = workflow([{"originalTags": {"copyright": ["foo_bar"], "character": ["foo bar"]}}])
        self.assertEqual(get_gallery_categories(graph, "20", "foo_bar, foo bar"), {})

    def test_only_actual_input_tokens_can_receive_metadata(self):
        graph = workflow([{"originalTags": {"copyright": ["red,blue"], "general": ["smile"]}}])
        self.assertEqual(get_gallery_categories(graph, "20", "red,blue, smile"), {"smile": "general"})

    def test_only_exact_tag_sequence_matches(self):
        graph = workflow([{"originalTags": {"copyright": ["arknights"], "general": ["smile"]}}])
        for tags in ["smile, arknights", "arknights", "arknights, smile, extra", None]:
            with self.subTest(tags=tags):
                self.assertEqual(get_gallery_categories(graph, "20", tags), {})

    def test_string_groups_use_gallery_whitespace_parsing(self):
        graph = workflow([{"originalTags": {"copyright": "series_a series_b", "character": ["person", 7, None]}}])
        self.assertEqual(get_gallery_categories(graph, "20", "series_a, series_b, person"), {
            "series a": "copyright", "series b": "copyright", "person": "character",
        })

    def test_missing_wrong_source_or_indirect_link_is_ignored(self):
        base = workflow([{"originalTags": {"copyright": ["arknights"]}}])
        variants = []
        for link in [["10", 0], ["10", True], ["missing", 1], ["20", 1], ["10"], "arknights", None]:
            graph = copy.deepcopy(base)
            graph["20"]["inputs"]["tags"] = link
            variants.append(graph)
        indirect = copy.deepcopy(base)
        indirect["10"]["class_type"] = "Reroute"
        indirect["10"]["inputs"]["tags"] = ["10", 1]
        variants.append(indirect)
        variants.extend([None, {}, {"20": {"inputs": None}}])
        for graph in variants:
            with self.subTest(graph=graph):
                self.assertEqual(get_gallery_categories(graph, "20", "arknights"), {})

    def test_malformed_or_unsupported_payload_returns_empty(self):
        invalid = ["not JSON", "[]", "{}", '{"version":2}', '{"version":true}',
                   '{"version":1,"prompt":[]}', '{"version":1,"selections":{}}',
                   '{"version":1,"selections":[null]}', ["linked", 0], None]
        for payload in invalid:
            with self.subTest(payload=payload):
                graph = workflow([])
                graph["10"]["inputs"]["gallery_payload"] = payload
                self.assertEqual(get_gallery_categories(graph, "20", "arknights"), {})


if __name__ == "__main__":
    unittest.main()
