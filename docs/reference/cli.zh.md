# 命令行参考

所有命令通过 `pixi run gaxis …` 运行（也可以直接调用已安装的 `gaxis`）。
失败时退出码非 0，错误打印为 `{"code", "message", "hint?"}`，`--json` 可机读。

## 全局

| 命令 | 作用 |
|---|---|
| `gaxis version` | 版本 |
| `gaxis config` | 生效配置（文件 + 环境变量） |
| `gaxis health` | 只读健康检查 |
| `gaxis tools` | 冻结的 MCP 工具契约（v2.1） |
| `gaxis presets` | 期刊预设几何与字号 |
| `gaxis palettes` | 调色板与色盲安全标记 |

## 渲染

### `gaxis describe --data TABLE`

给表做画像：列类型、基数、单位提示、推荐图型。

### `gaxis render --data TABLE [options]`

| 选项 | 说明 |
|---|---|
| `--chart {bar,stacked_bar,line,scatter,box,heatmap,network,tree}` | 图型（默认由数据推断；network/tree 需显式指定） |
| `--x/--y/--hue/--yerr/--weight/--annotation/--color-map/--rotate-labels` | 编码列名；`--color-map` 是类别→hex JSON；`--rotate-labels` 是 x 刻度旋转角度 |
| `--backend python\|r` | matplotlib 或 ggplot2 |
| `--preset NAME` | 期刊预设（默认 `default`） |
| `--palette NAME` | 覆盖预设调色板 |
| `--width/--height` | 覆盖预设几何（mm） |
| `--dpi` | 默认 600 |
| `--formats pdf,png` | 可组合 `pdf,svg,png,tiff` |
| `--annotate` | 在标记上打印数值 |
| `--out DIR` | 输出根目录（默认 `data/renders`） |
| `--source-asset ID` | 记录来源资产（选择反馈） |
| `--allow-lint-errors` | lint 问题时仍返回 0 |

### `gaxis lint PATHS… [--preset NAME] [--width MM --height MM]`

对已有产物做语言无关的发表级检查（L001–L009），可一次传多个文件。

## 计划与选择

### `gaxis plan "BRIEF" [--preset NAME] [--k N]`

数据无关的图计划 + 知识库匹配案例。适合在数据到位前与用户/宿主对齐。

### `gaxis kb search [QUERY] [options]`

| 选项 | 说明 |
|---|---|
| `--schema TABLE` | 用表结构检索（`QUERY` 可省略） |
| `--image PATH` | 用图检索（dHash 相似度） |
| `--chart TYPE` / `--min-level L1\|L2\|L3` | 过滤 |
| `--tier gold\|dense\|reject` | 设计分档过滤 |
| `--has-code/--no-code` | 是否有代码记录 |
| `--k N` | 返回数量（≤50） |
| `--sheet` | 生成编号 contact sheet 并打印路径 |
| `--json` | 机读输出 |

## 模板与适配

### `gaxis kb seed [--preset NAME]… [--backend python\|r]… [--force]`

为每个（预设 × 图型 × 后端）真渲染并验证模板，写入 `type: template` 页面。幂等。

### `gaxis kb adopt MANIFEST_ID [--code PATH] [--preset NAME]`

把已复现的论文脚本注册为模板。要求脚本通过 `DATA_PATH` 绑定输入，否则 `adoption_refused`。

### `gaxis adapt --data TABLE [options]`

| 选项 | 说明 |
|---|---|
| `--query TEXT` | 意图（如 `"grouped bar"`） |
| `--asset ID` | 指定模板页面 |
| `--preset NAME` / `--backend python\|r` | 选择模板族 |
| `--dry-run` | 只写脚本与 manifest，不执行 |
| `--json` | 机读输出 |

## 论文

### `gaxis ingest SOURCE [--mode kb_first\|full] [--with-code/--no-code]`

`SOURCE` 可以是 PDF 路径、DOI、arXiv id、PubMed id、PMC id 或 PDF URL。
`kb_first` 只解析图与 caption；`full` 还会下载 PDF、找仓库、挑脚本。

### `gaxis manifest MANIFEST_ID|PATH [--json]`

按 id 查看论文图的完整 manifest（代码候选、复现等级、评分）；也可以直接给渲染产物目录里的
`manifest.json` 路径，查看图/代码/数据 hash 与 lint。

### `gaxis reproduce MANIFEST_ID --code SCRIPT [--data FILE] [--engine podman\|local] [--allow-network]`

单图复现 → 分级 → 自动资产化 + KB 刷新。

### `gaxis recipe list` / `gaxis recipe render`

| 命令 | 说明 |
|---|---|
| `gaxis recipe list [--chart TYPE] [--json]` | 策展的"表 → 图"契约 |
| `gaxis recipe render amr-network --data edges.csv [--color-map palette.json] [--out DIR] [--dry-run]` | 检查必需列后出图 |

`recipe render` 与 MCP 的 `list_figure_recipes` / `render_figure_recipe` 使用同一套契约。

### `gaxis analysis list` / `gaxis analysis run`

| 命令 | 说明 |
|---|---|
| `gaxis analysis list [--json]` | 可用分析 recipe、输入契约、输出 |
| `gaxis analysis run amr-cooccurrence --input TABLE [--out DIR] [--min-prevalence F] [--min-support N] [--weight jaccard\|count]` | 表 → `nodes.csv` + `edges.csv` + `analysis.json` |
| `gaxis analysis run newick-to-table --input tree.nwk [--metadata META] [--out DIR]` | Newick → `tree_edges.csv`（parent、child、branch_length） |
| `gaxis analysis workflows` | 列出 Snakemake 工作流 recipe |
| `gaxis analysis scaffold snp-tree --out DIR --alignment FASTA [--container IMAGE] [--check]` | 生成并校验 IQ-TREE 工作流项目 |
| `gaxis analysis check DIR` | 用 `snakemake -n` 校验已有工作流 |

AMR recipe 只消费已有的基因结果（bacmap/ABRicate），不重跑 AMR 调用。渲染：
`--chart network --x source --y target --weight weight`。

### `gaxis reconstruct MANIFEST_ID [options]`

| 选项 | 说明 |
|---|---|
| `--data FILE` | 挂载进沙箱的输入表（`GAXIS_DATA`） |
| `--engine podman\|local` | 沙箱引擎 |
| `--rounds N` | 生成/修正轮数 |
| `--target F` | 达到该相似度提前停止 |
| `--repair` | 从作者脚本出发修复 |
| `--model NAME` | 覆盖配置的视觉/代码模型 |
| `--timeout S` / `--max-side PX` | 单请求超时与图片尺寸 |

### `gaxis reproduce-paper PAPER_ID [options]`

| 选项 | 说明 |
|---|---|
| `--data FILE` | 所有图共用的输入表 |
| `--synthetic` | 无数据时生成带标记的合成表 |
| `--min-confidence F` | 代码配对置信度阈值（默认 0.5） |
| `--limit N` | 最多处理多少张（默认 8） |
| `--engine podman\|local` | 覆盖配置 |
| `--force` | 重跑已 L1/L2 的图 |

## 拼版

### `gaxis compose --panels ID[,ID…] [options]`

| 选项 | 说明 |
|---|---|
| `--layout ROWSxCOLS` | 不传则自动 |
| `--preset NAME` | 合成页面预设 |
| `--width/--height` | 页面尺寸（mm） |
| `--uniform` | 按合成预设与单元格尺寸重渲染每个面板 |
| `--no-labels` | 不加 A/B/C |
| `--out DIR` | 输出目录 |

## 知识库

| 命令 | 作用 |
|---|---|
| `gaxis kb status` | 可达性、页数、缺失向量数 |
| `gaxis kb ingest [--force]` | 把所有 manifest 投影进 KB（幂等） |
| `gaxis kb seed` | 验证模板入库 |
| `gaxis kb adopt` | 论文脚本入库为模板 |
| `gaxis kb search` | 检索（见上） |

## 队列

| 命令 | 作用 |
|---|---|
| `gaxis ops enqueue SOURCE… [--kind ingest\|reproduce] [--mode …]` | 入队（去重） |
| `gaxis ops run [--limit N] [--retries N] [--stall-minutes N]` | 处理待办 |
| `gaxis ops verify` | 校验 `done` 作业的证据是否还在 |
| `gaxis ops status [--reset all\|SOURCE] [--json]` | 查看/重置 |

## 质量与设计（维护者工具）

| 命令 | 作用 |
|---|---|
| `gaxis quality sheet` | 生成人工排序表（Markdown + contact sheet） |
| `gaxis quality backfill [--workers N] [--force]` | 重算裁切质量 / 设计 / 有用性并重新入库 |
| `gaxis quality calibrate CSV` | 用人工排序拟合权重 |
| `gaxis design judge IMAGE` | 单图设计评审 |
| `gaxis design judge-dir DIR` | 批量评审并输出排序 CSV |
| `gaxis design candidates DIR` | 为外部图集生成编号 sheet |

## MCP server

```bash
export GAXIS_MCP_TOKEN="$(openssl rand -hex 24)"
gaxis-mcp --transport http --host 127.0.0.1 --port 8770
gaxis-mcp --transport http --uds /tmp/gaxis.sock
gaxis-mcp --transport stdio          # 仅本地调试
```

没有 token 会拒绝启动；HTTP 是生产路径。
