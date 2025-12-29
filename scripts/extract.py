#!/usr/bin/env python3
import sys
import re
import yaml
from pathlib import Path


def load_extractor(customer_id, base_dir):
    path = base_dir / "extractors" / f"{customer_id}.yaml"
    if not path.exists():
        return {"stop_markers": [], "drop_line_regex": []}
    default = {"stop_markers": [], "drop_line_regex": []}
    with open(path) as f:
        return yaml.safe_load(f) or default


def load_fixtures(customer_id, base_dir):
    fixture_dir = base_dir / "fixtures" / customer_id
    if not fixture_dir.exists():
        return []
    texts = []
    for path in sorted(fixture_dir.glob("*.txt")):
        texts.append(path.read_text())
    return texts


def extract_body(text, extractor):
    stop_markers = extractor.get("stop_markers", [])
    drop_patterns = []
    for p in extractor.get("drop_line_regex", []):
        try:
            drop_patterns.append(re.compile(p))
        except re.error as e:
            print(f"Invalid regex '{p}': {e}", file=sys.stderr)

    lines = text.splitlines()
    result = []

    for line in lines:
        if any(marker in line for marker in stop_markers):
            break
        if any(p.search(line) for p in drop_patterns):
            continue
        result.append(line)

    while result and not result[-1].strip():
        result.pop()
    while result and not result[0].strip():
        result.pop(0)

    return "\n".join(result)


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <customer_id>", file=sys.stderr)
        sys.exit(1)

    customer_id = sys.argv[1]
    base_dir = Path(__file__).resolve().parent.parent

    extractor = load_extractor(customer_id, base_dir)
    fixtures = load_fixtures(customer_id, base_dir)

    if not fixtures:
        print(f"No fixtures found for {customer_id}", file=sys.stderr)
        sys.exit(1)

    bodies = [extract_body(text, extractor) for text in fixtures]
    output = "\n\n---\n\n".join(bodies)

    preview_path = base_dir / "previews" / f"{customer_id}.txt"
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    preview_path.write_text(output + "\n")

    print(f"Extracted to {preview_path}")


if __name__ == "__main__":
    main()
