# Tutorials

The tutorials map to gaxis's two main workflows, the analysis-recipe bridge, and supporting capabilities. Each one can be run independently, but doing them in order works best.

| Section | What you get | Needs network | Needs KB |
|---|---|---|---|
| [01 Your first figure](01-first-figure.md) | One journal-ready figure + editable script + manifest | No | No |
| [02 Requirements/data → figure selection](02-plan-and-select.md) | Candidate figures, contact sheet, selection record | No | Yes |
| [03 Template adaptation](03-adapt-template.md) | Reuse validated template code with new data | No | Yes |
| [04 Paper reproduction → code onboarding](04-reproduce-paper.md) | L1/L2/L3 ratings, code assets, searchable pages | Yes | Yes |
| [05 Multi-panel composition](05-compose-panels.md) | One-page vector multi-panel figure + composite manifest | No | No |
| [06 Operations](06-operations.md) | Automated onboarding queue, scheduled tasks, self-healing checks | Yes | Yes |
| [07 LLM reconstruction](07-llm-reconstruction.md) | Figure code when author code is missing or broken (labelled `llm_*`) | Yes | No |
| [08 AMR co-occurrence network](08-amr-network.md) | Table → co-occurrence edges → network figure, no AMR re-calling | No | No |
| [09 SNP tree workflow](09-snp-tree-workflow.md) | Snakemake scaffold + validation, Newick conversion, annotated tree figure | No | No |
| [10 bacmap results to network](10-bacmap-export.md) | Real bacmap AMR tables → co-occurrence network, no re-calling | No | No |

## Recommended practice order

```text
01 ──► 02 ──► 03 ──► 05 ──► 08   (fully offline: build intuition first)
          └──► 04 ──► 06 ──► 07   (do these with a real paper)
```

## Structure shared by every section

- **Goal**: what you can verify once it's done;
- **Commands**: ready to copy and run;
- **What you should see**: what normal output looks like;
- **Checkpoint**: self-check with files/manifest fields, rather than "it looks right";
- **Common issues**: check here first when something fails.

!!! tip "Run `pixi run check` first"
    The tutorials assume the repository is currently green (ruff/mypy/pytest all pass). If anything fails, fix it before moving on —
    otherwise you won't be able to tell whether a problem is new or environmental.
