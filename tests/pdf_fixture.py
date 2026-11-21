"""Build a small but realistic paper PDF for the M1 parsing tests.

Layout per page is deliberately spatial: title, a body paragraph citing the figure,
the figure itself as an embedded raster image, its caption, then more body text.
That is exactly the geometry the caption/image association has to get right.
"""

from __future__ import annotations

from pathlib import Path


def build_sample_pdf(path: Path) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    matplotlib.rcParams["pdf.fonttype"] = 42
    matplotlib.rcParams["ps.fonttype"] = 42
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    figure_png = path.with_name("figure-source.png")
    chart = plt.figure(figsize=(4, 2.4), dpi=200)
    axis = chart.add_subplot(111)
    axis.bar(["WT", "dpsA", "rpoS", "hfq"], [120, 85, 150, 95], color="#009E73")
    axis.set_ylabel("expr fpkm")
    axis.set_xlabel("genotype")
    chart.savefig(figure_png, bbox_inches="tight")
    plt.close(chart)

    with PdfPages(path) as pdf:
        page = plt.figure(figsize=(8.27, 11.69))
        page.text(
            0.08,
            0.94,
            "Nitrogen stress reshapes the transcriptome of Vibrio parahaemolyticus",
            fontsize=15,
            weight="bold",
        )
        page.text(
            0.08,
            0.88,
            "We measured expression across four genotypes under three conditions (Fig. 1).",
            fontsize=10,
        )
        image = plt.imread(figure_png)
        axes = page.add_axes([0.12, 0.60, 0.76, 0.20])
        axes.imshow(image, aspect="auto")
        axes.axis("off")
        page.text(
            0.08,
            0.53,
            "Fig. 1. Grouped bar chart of expression (FPKM) across four genotypes and three "
            "nitrogen conditions; bars are means of four replicates and error bars are s.d.",
            fontsize=9,
        )
        page.text(
            0.08,
            0.44,
            "As shown in Fig. 1, rpoS expression increased under LB while dpsA declined.",
            fontsize=10,
        )
        page.text(
            0.08,
            0.40,
            "Data and code: https://github.com/example/figrepo.",
            fontsize=10,
        )
        page.text(
            0.08,
            0.36,
            "Fig. 2 in a companion paper reports the corresponding proteomics data.",
            fontsize=10,
        )
        pdf.savefig(page)
        plt.close(page)

        second = plt.figure(figsize=(8.27, 11.69))
        second.text(0.08, 0.9, "Methods", fontsize=14, weight="bold")
        second.text(
            0.08,
            0.84,
            "Strains were grown in M9 minimal medium at 30 degrees Celsius.",
            fontsize=10,
        )
        pdf.savefig(second)
        plt.close(second)
    return path


def _chart_png(directory: Path) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    target = directory / "chart.png"
    figure = plt.figure(figsize=(4, 2.4), dpi=200)
    axis = figure.add_subplot(111)
    axis.bar(["A", "B"], [3, 5])
    figure.savefig(target, bbox_inches="tight")
    plt.close(figure)
    return target


def build_caption_only_pdf(path: Path) -> Path:
    """A 'Figure legends' page: caption text, artwork delivered separately."""
    import matplotlib

    matplotlib.use("Agg")
    matplotlib.rcParams["pdf.fonttype"] = 42
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    with PdfPages(path) as pdf:
        page = plt.figure(figsize=(8.27, 11.69))
        page.text(0.08, 0.9, "Figure legends", fontsize=13, weight="bold")
        page.text(0.08, 0.84, "Fig. 1. Growth curves of four isolates over 24 h in M9.", fontsize=9)
        page.text(0.08, 0.79, "As shown in Fig. 1, growth stalled after 12 h.", fontsize=10)
        pdf.savefig(page)
        plt.close(page)
    return path


def build_split_layout_pdf(path: Path) -> Path:
    """Pre-proof layout: caption page first, then a page containing only the figure."""
    import matplotlib

    matplotlib.use("Agg")
    matplotlib.rcParams["pdf.fonttype"] = 42
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    chart = _chart_png(path.parent)

    with PdfPages(path) as pdf:
        legends = plt.figure(figsize=(8.27, 11.69))
        legends.text(0.08, 0.9, "Figure legends", fontsize=13, weight="bold")
        legends.text(
            0.08,
            0.84,
            "Fig. 1. Grouped bar chart of expression across two groups.",
            fontsize=9,
        )
        legends.text(0.08, 0.79, "Expression is shown in Fig. 1 for both groups.", fontsize=10)
        pdf.savefig(legends)
        plt.close(legends)

        artwork = plt.figure(figsize=(8.27, 11.69))
        axes = artwork.add_axes([0.1, 0.3, 0.8, 0.4])
        axes.imshow(plt.imread(chart))
        axes.axis("off")
        pdf.savefig(artwork)
        plt.close(artwork)
    return path
