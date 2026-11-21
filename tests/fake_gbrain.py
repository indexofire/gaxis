#!/usr/bin/env python3
"""Minimal gbrain CLI double used by the KB tests.

Implements only the operations gaxis calls: put, get, delete, search, call get_health.
State is a JSON file named by $FAKE_GBRAIN_STATE. Frontmatter parsing is deliberately
simple — gaxis generates the pages, so the format is known.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def load_state() -> dict:
    path = Path(os.environ["FAKE_GBRAIN_STATE"])
    if not path.is_file():
        return {"pages": {}}
    return json.loads(path.read_text())


def save_state(state: dict) -> None:
    path = Path(os.environ["FAKE_GBRAIN_STATE"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))


def split_frontmatter(markdown: str) -> tuple[dict, str]:
    if not markdown.startswith("---\n"):
        return {}, markdown
    end = markdown.find("\n---\n", 4)
    if end < 0:
        return {}, markdown
    raw = markdown[4:end]
    body = markdown[end + 5 :]
    front: dict = {}
    for line in raw.splitlines():
        if ": " not in line:
            continue
        key, value = line.split(": ", 1)
        value = value.strip()
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1].replace('\\"', '"')
        elif value == "null":
            front[key] = None
            continue
        elif value in {"true", "false"}:
            front[key] = value == "true"
            continue
        else:
            try:
                front[key] = float(value) if "." in value else int(value)
                continue
            except ValueError:
                pass
        front[key] = value
    return front, body


def option(args: list[str], name: str, default=None):
    if name in args:
        return args[args.index(name) + 1]
    return default


def options(args: list[str], name: str) -> list[str]:
    values = []
    for index, value in enumerate(args):
        if value == name and index + 1 < len(args):
            values.append(args[index + 1])
    return values


def main() -> int:
    args = sys.argv[1:]
    state = load_state()
    pages = state.setdefault("pages", {})
    command = args[0] if args else ""

    if command == "put":
        slug = args[1]
        markdown = sys.stdin.read()
        pages[slug] = {"markdown": markdown, "revision": f"rev-{len(pages) + 1}"}
        save_state(state)
        print(json.dumps({"slug": slug, "revision": pages[slug]["revision"]}))
        return 0

    if command == "get":
        slug = args[1]
        page = pages.get(slug)
        if page is None:
            print(f"Error [not_found]: no page {slug}", file=sys.stderr)
            return 1
        front, body = split_frontmatter(page["markdown"])
        print(
            json.dumps(
                {
                    "slug": slug,
                    "frontmatter": front,
                    "compiled_truth": body,
                    "revision": page["revision"],
                    "title": front.get("title"),
                    "type": front.get("type"),
                }
            )
        )
        return 0

    if command == "delete":
        slug = args[1]
        pages.pop(slug, None)
        save_state(state)
        print(json.dumps({"status": "soft_deleted", "slug": slug}))
        return 0

    if command == "search":
        query = args[1].lower()
        limit = int(option(args, "--limit", 10))
        wanted_types = options(args, "--types")
        filters = dict(item.split("=", 1) for item in options(args, "--where"))
        words = [word for word in query.replace(",", " ").split() if len(word) > 2]
        results = []
        for slug, page in pages.items():
            front, body = split_frontmatter(page["markdown"])
            if wanted_types and str(front.get("type")) not in wanted_types:
                continue
            if any(str(front.get(key)) != value for key, value in filters.items()):
                continue
            haystack = f"{front.get('title', '')} {body}".lower()
            matches = sum(1 for word in words if word in haystack)
            score = matches / max(len(words), 1)
            if score <= 0:
                continue
            results.append(
                {
                    "slug": slug,
                    "title": front.get("title"),
                    "score": round(score, 3),
                    "type": front.get("type"),
                    "chunk_text": body[:200],
                    "trust_tier": "external_untrusted",
                    "source_id": slug.split(":")[0],
                }
            )
        results.sort(key=lambda item: item["score"], reverse=True)
        print(json.dumps(results[:limit]))
        return 0

    if command == "call":
        operation = args[1] if len(args) > 1 else ""
        if operation == "get_health":
            print(
                json.dumps(
                    {
                        "page_count": len(pages),
                        "missing_embeddings": 0,
                        "embed_coverage": 1,
                    }
                )
            )
            return 0
        print(json.dumps({}))
        return 0

    print(f"fake gbrain: unsupported command {args}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
