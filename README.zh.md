# gaxis

[English](README.md) | 简体中文

[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![Docs](https://img.shields.io/badge/docs-indexofire.github.io%2Fgaxis-4f46e5.svg)](https://indexofire.github.io/gaxis/)

将论文图表转化为**经过验证、可复用的出版级图表代码**——并以相同的视觉语法渲染你自己的数据。

一个核心之上的两个入口界面：

| 入口界面 | 使用者 | 输入 | 输出 |
|---|---|---|---|
| MCP 服务器（Streamable HTTP） | bacmap、DSH、Pi、Hermes、任意 MCP 客户端 | 数据路径 / 论文查询 | 图表 + 代码 + manifest |
| CLI | 终端中的研究人员 | `results.csv` | 出版级图表 + 可编辑脚本 |

## 状态

**0.1.0** — 核心闭环已端到端跑通：

- 确定性流水线：数据 → spec → 独立脚本 → 图表 → 出版级 lint（L001–L009）→ 携带数据/代码哈希的 `manifest.json`；六种图表类型 × matplotlib/ggplot2 × 七种预设；
- 论文侧：标识符解析、受限 PDF 下载、图表/图注/引用段落提取、代码仓库链接 + 绘图脚本发现；
- 复现：无 root 的 podman 沙箱、相似度分解、L1/L2/L3、代码资产化；
- 知识库：gbrain `paper-kb` 页面、嵌入向量、文本/schema/图像检索、84 个经验证模板（`kb seed`）、论文脚本采纳（`kb adopt`）；
- 选择与适配：`plan_chart_from_brief`、候选 contact sheet 拼版、`adapt_chart_code`、多面板 `compose`（含 `--uniform`）；
- 运维：带检查点的 ingest/reproduce 队列、重试、停滞回收、心跳、`ops verify`；
- 入口界面：CLI 与 MCP 服务器（十个工具，契约 v2.1）+ 类型化客户端 + bacmap 适配器。

CLI/bacmap 之外的 M5 宿主适配器以及更深入的 M6 自愈层仍在开发中；已知限制见 [CHANGELOG.md](CHANGELOG.md#known-limits-in-010)。

文档：用户指南与教程位于 [`docs/`](docs/index.zh.md)（MkDocs Material：`pixi run docs-serve` / `pixi run docs-build`）。架构与 ADR 见 [DESIGN.md](DESIGN.md)；贡献者规则见 [AGENTS.md](AGENTS.md)。

## 快速开始

```bash
pixi install                          # python 3.12 + matplotlib + R/ggplot2
pixi run gaxis presets                # available journal presets
pixi run gaxis describe --data examples/demo/expr.tsv
pixi run gaxis render --data examples/demo/expr.tsv --chart bar \
  --x genotype --y expr_fpkm --hue condition --preset nature_microbiology \
  --out data/demo
pixi run gaxis render --data examples/demo/expr.tsv --preset asm \
  --backend r --out data/demo-r            # same figure via ggplot2
pixi run gaxis tools                   # frozen MCP contract + data classes
cp gaxis.example.toml gaxis.toml     # confirmation threshold, ingest mode, gbrain wiring
pixi run gaxis config                # effective configuration
pixi run gaxis plan "grouped bar chart with error bars, Nature Microbiology"
pixi run gaxis ingest examples/demo/paper.pdf --mode full   # paper -> figures + manifests
pixi run gaxis ingest 10.1099/mgen.0.000001      # DOI -> open-access PDF -> figures -> repo code
pixi run gaxis manifest pdf-<sha8>/fig-1
pixi run gaxis reproduce pdf-<sha8>/fig-1 --code examples/demo/figure.py --engine podman
pixi run gaxis reproduce pdf-<sha8>/fig-1 --code examples/demo/figure.R --engine podman
pixi run gaxis quality sheet            # ranking sheet (design columns; extraction is the gate)
pixi run gaxis design candidates <dir>  # numbered sheet for a curated golden set
pixi run gaxis design judge <image>     # score one figure with the configured vision judge
pixi run gaxis kb seed                     # verified templates for adapt_chart_code
pixi run gaxis adapt --data examples/demo/expr.tsv --preset asm --query "bar chart"
pixi run gaxis kb adopt pdf-<sha8>/fig-1 --code examples/demo/figure.py  # paper script -> template
pixi run gaxis kb search --schema examples/demo/expr.tsv --sheet  # choose from the KB by table shape
pixi run gaxis reproduce-paper pdf-<sha8> [--synthetic]       # reproduce a paper's figures
pixi run gaxis compose --panels a,b --layout 1x2 --preset nature_microbiology
pixi run gaxis ops enqueue <doi> examples/demo/paper.pdf && pixi run gaxis ops run
pixi run gaxis health                  # read-only probe

# knowledge base (gbrain), installed into the pixi env
pixi run gbrain-install && pixi run gbrain-init
pixi run gbrain search "rarefaction curve" --source-id paper-kb --json

# as a tool for bacmap / any MCP host
export GAXIS_MCP_TOKEN="$(openssl rand -hex 24)"
pixi run gaxis-mcp --transport http --port 8770
pixi run gaxis lint data/demo/<figure-id>/figure.pdf
pixi run check                        # ruff + mypy + pytest
pixi run review                       # 36-figure matrix + contact sheet for human review
```

每次渲染都会写出一个自包含的目录：

```
data/demo/<figure-id>/
  figure.py | figure.R   # the deliverable: readable, runnable, no gaxis import
  figure.pdf figure.svg figure.png
  manifest.json          # spec + data sha256 + code sha256 + outputs + lint report
```

产出图像的那个脚本就是你最终得到的脚本。不存在可能与产物产生偏差的第二次生成步骤。

## 文档

用户指南与教程使用 MkDocs Material 构建：

```bash
pixi run docs-serve   # preview at http://127.0.0.1:8000/gaxis/
pixi run docs-build   # strict build into site/
```

从 `docs/index.md` 开始；教程涵盖首张图表、选择、模板适配、论文复现、组合与运维。内部契约保留在 `docs/*.md` 之下。

## 设计说明

- `ChartSpec` 是唯一的中间表示；生产者（内置模板、知识库资产、论文复现）从不直接与渲染器对话。
- `style/presets/*.toml` 编码了期刊的版面几何参数（宽度以 mm 计、字号以 pt 计、调色板、轴线、矢量字体嵌入）— 微生物学优先：Nature Microbiology、ASM（mBio/AEM）、ISME J、Cell Host & Microbe、Microbial Genomics。
- `style/lint.py` 是“出版级”的可度量形式：矢量输出、DPI、嵌入字体（无 Type 3）、图表几何、色盲安全、必需文本标签。
- `manifest.json` 携带 `data.sha256` + `code.sha256` + lint 报告，因此任何交付的图表都可追溯审计至其输入（ADR-08）。
- 两种后端的聚合方式完全一致（均值 + 标准差，或提供的 `yerr` 列），并在未给出数值度量时回退到计数模式，因此 matplotlib 图表与其 ggplot2 孪生版本是可比较的，而不仅仅是相似。
- MCP 工具声明 `data_class`（`D1`–`D4`）和副作用，因此像 bacmap 这样的宿主可以在调用触及本地数据**之前**强制执行其 profile 上限。
