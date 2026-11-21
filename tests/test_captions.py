"""Caption/citation heuristics (no PDF library involved)."""

from gaxis.parse import captions


def test_label_parsing_variants() -> None:
    assert captions.parse_label("Fig. 3. Grouped bars") == (3, "Grouped bars")
    assert captions.parse_label("Figure 12A: rarefaction curves") == (12, "rarefaction curves")
    assert captions.parse_label("图 2 不同处理下的表达量") == (2, "不同处理下的表达量")
    assert captions.parse_label("Supplementary Fig. S1. extra") is None
    assert captions.parse_label("Body text mentioning Fig. 3 mid-sentence") is None


def test_mention_detection_does_not_confuse_figure_1_and_10() -> None:
    assert captions.mentions_figure("as in Fig. 1", 1) is True
    assert captions.mentions_figure("as in Fig. 10", 1) is False
    assert captions.mentions_figure("see Figure 10A", 10) is True
    assert captions.mentions_figure("no reference here", 1) is False


def test_join_blocks_undoes_hyphenation_and_normalises_space() -> None:
    merged = captions.join_blocks(
        ["Rarefaction curves of the", "16S amplic-\nons", "under three treatments"]
    )
    assert "amplicons" in merged
    assert "  " not in merged


def test_extract_citations_skips_captions_and_keeps_order() -> None:
    blocks = [
        "Fig. 1. Caption text mentioning Fig. 1 itself.",
        "First paragraph citing Fig. 1.",
        "Unrelated paragraph.",
        "Second paragraph citing Figure 1A.",
    ]
    found = captions.extract_citations(blocks, 1)
    assert found[0] == "First paragraph citing Fig. 1."
    assert len(found) == 2
