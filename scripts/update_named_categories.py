"""Build the offline copyright/character lookup from a pinned Danbooru CSV."""

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path


SOURCE_SHA256 = "175d0a30f260318fedef95d7ce9b1f250dda89ea55e437c0a6c3b7571bb91e34"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "tags_database" / "named_categories.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Downloaded source CSV; see NAMED_CATEGORIES.md")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--sha256", default=SOURCE_SHA256, help="Expected source checksum")
    args = parser.parse_args()

    raw = args.source.read_bytes()
    actual_sha256 = hashlib.sha256(raw).hexdigest()
    if actual_sha256 != args.sha256:
        parser.error(f"Source SHA-256 mismatch: {actual_sha256}")

    categories = {"3": set(), "4": set()}
    for row in csv.reader(io.StringIO(raw.decode("utf-8-sig"))):
        if len(row) >= 2 and row[1] in categories:
            name = row[0].strip()
            if name:
                categories[row[1]].add(name)

    if not all(categories.values()):
        parser.error("Source must include both copyright (3) and character (4) tags")
    if categories["3"] & categories["4"]:
        parser.error("Source assigns conflicting copyright/character categories")

    data = {
        "version": 1,
        "copyright": sorted(categories["3"]),
        "character": sorted(categories["4"]),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(data['copyright'])} copyright and {len(data['character'])} character tags")


if __name__ == "__main__":
    main()
