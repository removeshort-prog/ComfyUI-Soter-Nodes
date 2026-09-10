"""Read category metadata for the current direct Booru Gallery prompt output.

This adapter follows the Gallery version-1 prompt contract without importing
the other plugin or accessing its image files, services, or network clients.
"""

import json


CATEGORY_ORDER = ("artist", "copyright", "character", "general", "meta")
DEFAULT_CATEGORIES = ("copyright", "character", "general")


def _normalize_tag(tag):
    return tag.strip().lower().replace("\\(", "(").replace("\\)", ")").replace("_", " ")


def _tag_list(value):
    if isinstance(value, str):
        value = value.split()
    if not isinstance(value, (list, tuple)):
        return []
    return list(dict.fromkeys(item.strip() for item in value if isinstance(item, str) and item.strip()))


def _payload_for_direct_gallery(prompt, unique_id):
    if not isinstance(prompt, dict) or unique_id is None:
        return None
    current = prompt.get(str(unique_id))
    if not isinstance(current, dict) or not isinstance(current.get("inputs"), dict):
        return None
    link = current["inputs"].get("tags")
    if not isinstance(link, (list, tuple)) or len(link) != 2 or type(link[1]) is not int or link[1] != 1:
        return None
    source_id = str(link[0])
    if source_id == str(unique_id):
        return None
    source = prompt.get(source_id)
    if not isinstance(source, dict) or source.get("class_type") != "BooruGalleryNode":
        return None
    inputs = source.get("inputs")
    if not isinstance(inputs, dict) or not isinstance(inputs.get("gallery_payload"), str):
        return None
    try:
        payload = json.loads(inputs["gallery_payload"])
    except (ValueError, TypeError, RecursionError):
        return None
    if not isinstance(payload, dict) or type(payload.get("version")) is not int or payload["version"] != 1:
        return None
    if not isinstance(payload.get("prompt", {}), dict) or not isinstance(payload.get("selections", []), list):
        return None
    if not all(isinstance(selection, dict) for selection in payload.get("selections", [])):
        return None
    return payload


def _render_selection(selection, options):
    enabled = set(_tag_list(options.get("categories", list(DEFAULT_CATEGORIES))))
    excluded = set(_tag_list(options.get("excludedTags", [])))
    excluded.update(_tag_list(options.get("outputFilterTags", [])))
    edited = selection.get("editedTags")
    groups = edited if isinstance(edited, dict) else selection.get("originalTags")
    if not isinstance(groups, dict):
        groups = {}

    seen = set()
    rendered_tags = []
    classifications = {}
    ambiguous = set()
    for kind in CATEGORY_ORDER:
        if kind not in enabled:
            continue
        for tag in _tag_list(groups.get(kind, [])):
            if tag in excluded or tag in seen:
                continue
            seen.add(tag)
            rendered = tag.replace("_", " ") if options.get("replaceUnderscores", False) else tag
            if options.get("escapeParentheses", False):
                rendered = rendered.replace("(", "\\(").replace(")", "\\)")
            rendered_tags.append(rendered)
            key = _normalize_tag(rendered)
            if key in classifications and classifications[key] != kind:
                ambiguous.add(key)
            classifications[key] = kind
    for key in ambiguous:
        classifications.pop(key, None)
    return ", ".join(rendered_tags), classifications


def _prompt_tag_sequence(tags):
    return [_normalize_tag(tag) for tag in tags.split(",") if tag.strip()]


def get_gallery_categories(prompt, unique_id, tags):
    """Return only categories attached to the Gallery selection producing tags.

    Each selected image is matched independently. If multiple selections emit
    the same normalized text, only category assignments shared by all matches
    are retained. No category is inferred from unrelated selections.
    """
    if not isinstance(tags, str):
        return {}
    payload = _payload_for_direct_gallery(prompt, unique_id)
    if payload is None:
        return {}
    actual = _prompt_tag_sequence(tags)
    actual_names = set(actual)
    options = payload.get("prompt", {})
    agreed = None
    for selection in payload.get("selections", []):
        rendered, categories = _render_selection(selection, options)
        if _prompt_tag_sequence(rendered) != actual:
            continue
        categories = {name: kind for name, kind in categories.items() if name in actual_names}
        if agreed is None:
            agreed = dict(categories)
        else:
            agreed = {name: kind for name, kind in agreed.items() if categories.get(name) == kind}
    return agreed or {}
