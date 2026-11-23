# 08 AMR 共现网络（bacmap 表）

## 目标

直接使用 bacmap 中已有的 AMR 结果（或其他 AMR 筛查表）计算基因共现，并渲染发表级网络图，
**不重跑 ABRicate/AMRFinder**。这是第一个"分析 recipe"：表 → 表，再由 gaxis 出图。

## 输入契约

每个样本观察到的每个基因一行（长表）：

```csv
sample,gene,gene_class
S1,blaCTX-M,beta-lactam
S1,blaTEM,beta-lactam
S1,sul1,sulfonamide
...
```

- `sample` 别名：`sample_id`、`genome`、`isolate`、`strain`；
- `gene` 别名：`amr_gene`、`feature`、`determinant`；
- 可选类别列：`gene_class`、`class`、`category`、`resistance_class`。

未出现的基因视为不存在。recipe **不调用** AMR 工具，只消费其输出。

## 运行分析

```bash
pixi run gaxis analysis run amr-cooccurrence \
  --input amr_long.csv --out data/analysis \
  --min-prevalence 0.05 --min-support 2 --weight jaccard
```

输出：

```
data/analysis/<run_id>/
  nodes.csv     gene,samples,prevalence,gene_class
  edges.csv     source,target,weight,support,jaccard
  analysis.json 输入 sha256、参数、计数、工具版本
```

边表示共享样本数 ≥ `--min-support` 的基因对，`weight` 记录 Jaccard（或共享计数）。

## 渲染网络

```bash
pixi run gaxis render \
  --data data/analysis/<run_id>/edges.csv \
  --chart network --x source --y target --weight weight \
  --color-map data/analysis/<run_id>/palette.json \
  --preset asm --out data/figures
```

- 环形布局；边宽/透明度由 `weight` 决定，节点大小由度数决定；
- 节点颜色来自 `palette.json`（每个 gene class 一个颜色），同一 `--color-map` 可复用于树图等；
- matplotlib 与 ggplot2 双后端（同一数据契约）；
- 产物仍是标准交付：`figure.py` / `figure.R`、PDF/SVG/PNG/TIFF、lint、manifest。

## 刻意不做的事

- 不做组装、分型、AMR 调用、基因组 QC——bacmap/gmlst/gspec/gside 已经完成；
- 不凭空造边：表就是证据，`analysis.json` 记录输入 hash；
- 不硬编码结果：换 `edges.csv` 重新渲染，图就变。

## 检查点

- [ ] `nodes.csv`/`edges.csv` 存在，`analysis.json` 有输入 sha256；
- [ ] 两个后端 `render` 的 lint 都是 clean；
- [ ] `manifest.json` 含数据/代码 hash；
- [ ] 改 `--min-support` 会改变边数，而不只是画法。

## 常见问题

**`data_contract_violation`**：表头缺少 sample/gene 列；检查别名。

**`no_edges_pass_filter`**：降低 `--min-support`/`--min-prevalence`；稀疏矩阵可能确实没有共现对。

**标签重叠**：环形布局把标签放在圆外；基因很多时按类别拆分面板或只画 top 类别。
