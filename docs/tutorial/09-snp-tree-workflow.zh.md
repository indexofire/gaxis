# 09 SNP 树工作流（Snakemake）

## 目标

对于 gaxis 不自带的工具（IQ-TREE、比对工具），gaxis **生成并校验 Snakemake 工作流**；
bacmap（或你）执行它，得到的树再作为图的数据。gaxis 不实现系统发育算法。

## 生成项目

```bash
pixi run gaxis analysis scaffold snp-tree \
  --out workflows/snp-tree \
  --alignment alignment.fasta \
  --container docker://<固定的-iqtree-镜像> \
  --threads 8 --check
```

写入：

```
workflows/snp-tree/
  Snakefile
  config.yaml        alignment、model、bootstrap、threads、seed、container
  README.md
  workflow.json      recipe id、版本、输入/输出、文件 sha256
```

`--check` 运行 `snakemake -n`（dry run），只校验配置与 DAG，不执行工具。

## 运行

```bash
cd workflows/snp-tree
snakemake --cores 8
```

输出：

```
results/tree.nwk
results/iqtree.log
```

- 在另一台机器运行前，把 `container` 设为**固定**的 IQ-TREE 镜像（最好用 digest）。
- `metadata` 可选，留给下一步的树注释。
- bacmap 可以调度同一个 Snakefile；gaxis 不在执行路径里。

## 合并 tip metadata（可选）

```bash
pixi run gaxis analysis run newick-to-table \
  --input results/tree.nwk --metadata metadata.csv --out data/analysis
```

`metadata.csv` 需要一个 key 列（`tip`、`sample`、`id`、`name`、`genome`、`strain` 或 `isolate`）
以及任意注释列；值会复制到 tip 行，树表因此多出 `source`、`amr_class` 等列。缺失的 tip 会写入
运行目录的 `metadata_missing.txt`，不猜。

## 渲染树

```bash
pixi run gaxis analysis run newick-to-table \
  --input results/tree.nwk --out data/analysis

pixi run gaxis render \
  --data data/analysis/<run_id>/tree_edges.csv \
  --chart tree --x parent --y child --weight branch_length \
  --hue source --annotation amr_class --preset asm --out data/figures
```

矩形进化树；分支长度来自 `branch_length`，tip 标签自动放置；`--hue source` 与
`--annotation amr_class` 在 tip 旁各画一条色带（`--annotation` 可重复）并生成合并图例。matplotlib 与 ggplot2 双后端。树本身仍由 IQ-TREE 生成，gaxis 只做布局与出图。

![带注释的树图示例](/gaxis/assets/example-tree.png)

## 校验已有项目

```bash
pixi run gaxis analysis check workflows/snp-tree
```

## gaxis 做/不做什么

| 做 | 不做 |
|---|---|
| 生成 Snakefile + 配置 + 使用说明 | 运行 IQ-TREE 或比对工具 |
| 用 `snakemake -n` 校验 DAG | 发明系统发育参数 |
| 记录输入、输出、文件 hash | 隐藏工具版本（container 显式） |

## 检查点

- [ ] `workflow.json` 含输入、输出与 `files_sha256`；
- [ ] `gaxis analysis check` 返回 `workflow OK`；
- [ ] `snakemake -n` 列出两个期望输出；
- [ ] 真实运行后 `results/tree.nwk` 存在，container 已固定。

## 下一步

多列注释条（source + AMR class + 型别并排）以及与 AMR 网络图共享图例是下一步；单列注释与工作流
输出已经是稳定契约。
