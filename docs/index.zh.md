# gaxis

**把一张整洁的数据表变成期刊级的图，并把生成它的脚本一起交给你；把论文里的图变成可复现、可检索、可复用的代码。**

gaxis 有两个使用面，共享同一个内核：

| 使用面 | 适合谁 | 入口 |
|---|---|---|
| **CLI** | 坐在终端里的研究者，离线、不需要知识库 | `pixi run gaxis …` |
| **MCP server** | bacmap、Pi、DSH、Hermes 等宿主，Streamable HTTP + Bearer | `pixi run gaxis-mcp` |

核心原则只有一句：

> 图、脚本、manifest 是同一个产物。任何两者可能漂移的设计都是错的。

![示例图](/gaxis/assets/example-figure.png)

## 它能做什么

- **出图**：6 种图型 × matplotlib / ggplot2 双后端 × 7 个微生物学期刊预设，PDF/SVG/PNG/TIFF，逐项发表级 lint（L001–L009）。
- **可交付代码**：每张图都带一个独立的 `figure.py` / `figure.R`，不 import gaxis，拿到任何 Python/R 环境都能跑。
- **证据绑定**：每次渲染写 `manifest.json`，包含数据 hash、代码 hash、输出几何和 lint 报告。
- **选图**：给一句话需求，或只给一张数据表，就能从知识库里取候选图，生成编号 contact sheet，选一张再出图。
- **复现论文图**：解析 PDF → 找图、caption、引用段、代码仓库 → podman 沙箱跑 → 视觉比对 → L1/L2/L3 分级。
- **LLM 重建回退**：作者代码缺失或跑不起来时，视觉模型写新脚本，交给同一沙箱评判；manifest 记录 `method = llm_reconstruction`/`llm_repair`，绝不写成 `author_code`。
- **代码入库**：复现成功的脚本自动复制进资产库、刷新 KB 页面；验证过的模板可以用新数据重新绑定（`adapt`）。
- **拼版**：把已渲染面板摆到一页（矢量保留），可选 `--uniform` 统一字号与几何。
- **队列与自愈**：检查点式入库/复现队列、重试、停滞回收、心跳、证据校验。

## 60 秒上手

```bash
# 1. 环境（pixi 会装好 python 3.12、matplotlib、R + ggplot2）
pixi install
pixi run check                      # ruff + mypy + 全部测试

# 2. 用示例数据出一张 Nature Microbiology 风格柱状图
pixi run gaxis render --data examples/demo/expr.tsv --preset nature_microbiology --out data/demo

# 3. 看它交给你什么
ls data/demo/<figure-id>/            # figure.py  <figure-id>.pdf  manifest.json
```

没有 `examples/demo` 时，任意一张 CSV/TSV 都可以：

```bash
pixi run gaxis describe --data my_table.csv
pixi run gaxis render --data my_table.csv --preset asm --out out/
```

## 知识库（可选，但推荐）

```bash
pixi run gbrain-install      # 首次：内置 gbrain + 固定版本 bun
pixi run gbrain-init         # 在 ~/.local/share/gaxis/gbrain 建库
pixi run gaxis kb seed       # 84 个已验证模板（约 2–3 分钟，可离线）
pixi run gaxis kb status     # 96 pages, missing_embeddings=0
```

知识库是**可重建的产物**，不随仓库分发；页面由 manifest 生成，清掉后重跑上面三步即可。

## 从哪里开始

- 第一次使用 → [快速开始](quickstart.zh.md)
- 想知道"图/脚本/manifest 为什么绑在一起" → [核心概念](concepts.zh.md)
- 想跟着做一遍 → [教程](tutorial/index.zh.md)
- 查命令与配置 → [命令行](reference/cli.zh.md) · [配置](reference/configuration.zh.md)
- 给宿主接 MCP → [MCP 工具契约](mcp-tools.zh.md)

## 明确的非目标

gaxis 不做物种/基因组数据获取、不做分析管线、不做元数据库，也不在渲染路径里调用 LLM。图是确定性的：给定 manifest，同一版本应能字节级复现。
