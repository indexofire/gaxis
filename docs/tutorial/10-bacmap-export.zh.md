# 10 bacmap 结果 → gaxis 网络图

## 目标

直接使用 **bacmap 已完成的 run** 中的 AMR 结果，而不是原始 reads：导出表 → 计算共现 → 出发表级网络图。
不重跑任何 AMR 工具。

## 导出表

```bash
python integrations/bacmap_export.py \
  --run-dir ~/.local/share/bacmap/results/runs/<run-id> \
  --out data/bacmap-export
```

输出：

```
data/bacmap-export/amr_long.csv   sample,gene,gene_class
data/bacmap-export/metadata.csv   sample,species,serotype
data/bacmap-export/export.json    samples、amr_rows、来源
```

参考适配器约 100 行，只用标准库，不 import bacmap 或 gaxis。bacmap 内部也可以用其 query/result 工具
生成同样的表；契约就是这两个 CSV。

## 分析与出图

```bash
pixi run gaxis analysis run amr-cooccurrence \
  --input data/bacmap-export/amr_long.csv --out data/analysis \
  --min-prevalence 0.3 --min-support 2

pixi run gaxis render \
  --data data/analysis/<run_id>/edges.csv \
  --chart network --x source --y target --weight weight \
  --color-map data/analysis/<run_id>/palette.json \
  --preset asm --out data/figures
```

真实例子（20 株 Salmonella、121 条 AMR 记录；`--min-prevalence 0.3` 下 9 个基因、20 条边）：

![bacmap 网络图示例](/gaxis/assets/example-bacmap-network.png)

`--min-prevalence` 既是科学选择也是排版选择：调低会显示更多基因、网络更密；主图可调高，密集版本放补充材料。

## 仍留在 bacmap 的事

- 组装、分型、血清型、AMR 调用、cgMLST；
- 样本/run 元数据与访问控制；
- 决定哪些样本进入这张图。

gaxis 只看到导出的表，计算共现，并在 `analysis.json` 记录输入 hash。

## 检查点

- [ ] `export.json` 有 run 路径与行数；
- [ ] `amr_long.csv` 是"样本 × 观测基因"长表；
- [ ] `analysis.json` 有输入 sha256 与参数；
- [ ] 图 manifest 有数据/代码 hash，lint clean。
