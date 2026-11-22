"""Newick -> edge table (parent, child, branch_length, is_tip).

This is a format conversion, not phylogenetics: the tree is produced upstream
(IQ-TREE via the Snakemake workflow) and gaxis only lays it out for a figure.
"""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import __version__
from ..errors import GaxisError
from ..models.analysis import AnalysisRun

RECIPE_TREE = {
    "id": "newick-to-table",
    "title": "Newick tree -> edge table",
    "input": ".nwk/.newick/.tree Newick file",
    "outputs": ["tree_edges.csv"],
    "params": [],
    "engine": "python (stdlib only)",
    "note": "layout/format conversion only; the tree itself comes from IQ-TREE or bacmap",
}


@dataclass
class _Node:
    name: str
    length: float | None = None
    children: list[_Node] = field(default_factory=list)


class _Parser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.position = 0

    def peek(self) -> str:
        return self.text[self.position : self.position + 1]

    def skip_ws(self) -> None:
        # NOTE: `"" in " \t\r\n"` is True; guard the end of input explicitly.
        while self.position < len(self.text) and self.text[self.position] in " \t\r\n":
            self.position += 1

    def take(self) -> str:
        char = self.peek()
        self.position += 1
        return char

    def parse(self) -> _Node:
        node = self._node()
        self.skip_ws()
        if self.peek() == ";":
            self.position += 1
        if self.position < len(self.text) and self.text[self.position :].strip():
            raise GaxisError("tree_parse_failed", "unexpected characters after the Newick tree")
        return node

    def _node(self) -> _Node:
        self.skip_ws()
        children: list[_Node] = []
        if self.peek() == "(":
            self.take()
            while True:
                children.append(self._node())
                self.skip_ws()
                if self.peek() == ",":
                    self.take()
                    continue
                if self.peek() == ")":
                    self.take()
                    break
                raise GaxisError("tree_parse_failed", "expected ',' or ')' in Newick")
        name = ""
        self.skip_ws()
        if self.peek() == "'":
            self.take()
            name = self._quoted()
        else:
            start = self.position
            while self.position < len(self.text) and self.peek() not in ",():;":
                self.position += 1
            name = self.text[start : self.position].strip()
        length = None
        self.skip_ws()
        if self.peek() == ":":
            self.take()
            start = self.position
            while self.position < len(self.text) and self.peek() not in ",():;":
                self.position += 1
            raw = self.text[start : self.position].strip()
            try:
                length = float(raw)
            except ValueError as exc:
                raise GaxisError("tree_parse_failed", f"bad branch length {raw!r}") from exc
        return _Node(name=name, length=length, children=children)

    def _quoted(self) -> str:
        value = []
        while self.position < len(self.text):
            char = self.take()
            if char == "'":
                if self.peek() == "'":
                    value.append("'")
                    self.take()
                    continue
                return "".join(value)
            value.append(char)
        raise GaxisError("tree_parse_failed", "unterminated quoted name")


def _assign_names(root: _Node) -> None:
    counter = 0
    seen: set[str] = set()

    def walk(node: _Node) -> None:
        nonlocal counter
        name = node.name
        if not name:
            counter += 1
            name = f"node{counter}"
        while name in seen:
            counter += 1
            name = f"{name}_{counter}"
        node.name = name
        seen.add(name)
        for child in node.children:
            walk(child)

    walk(root)


def parse_newick(text: str) -> list[dict[str, Any]]:
    text = text.strip()
    if not text:
        raise GaxisError("tree_parse_failed", "empty Newick")
    # strip Newick comments [&...]; they are metadata, not topology
    while "[" in text and "]" in text:
        start = text.index("[")
        end = text.index("]", start)
        text = text[:start] + text[end + 1 :]
    root = _Parser(text).parse()
    _assign_names(root)
    edges: list[dict[str, Any]] = []

    def walk(node: _Node) -> None:
        for child in node.children:
            edges.append(
                {
                    "parent": node.name,
                    "child": child.name,
                    "branch_length": round(child.length if child.length is not None else 1.0, 8),
                    "is_tip": int(not child.children),
                }
            )
            walk(child)

    walk(root)
    if not edges:
        raise GaxisError("tree_parse_failed", "the Newick tree has no branches")
    return edges


def run_newick_to_table(input_path: Path, *, out_dir: Path) -> AnalysisRun:
    if not input_path.is_file():
        raise GaxisError("data_not_found", f"tree file not found: {input_path}")
    edges = parse_newick(input_path.read_text(encoding="utf-8", errors="replace"))
    digest = hashlib.sha256(input_path.read_bytes()).hexdigest()
    run_id = hashlib.sha256(f"newick-to-table-v1:{digest}".encode()).hexdigest()[:10]
    target = out_dir / run_id
    target.mkdir(parents=True, exist_ok=True)
    path = target / "tree_edges.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["parent", "child", "branch_length", "is_tip"])
        writer.writeheader()
        writer.writerows(edges)
    run = AnalysisRun(
        run_id=run_id,
        recipe="newick-to-table",
        input_path=str(input_path),
        input_sha256=digest,
        params={},
        samples=0,
        genes=0,
        edges=len(edges),
        outputs={"tree_edges": str(path)},
        tool=f"gaxis {__version__}",
    )
    (target / "analysis.json").write_text(run.model_dump_json(indent=2), encoding="utf-8")
    return run
