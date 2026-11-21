# 01 第一张图：数据到交付

## 目标

用一张 CSV/TSV 表生成期刊级图，得到三样东西：图、独立脚本、manifest。然后改脚本、重新跑、确认结果仍然可控。

## 准备数据

任何整洁表都可以。示例数据：

```text
sample,genotype,condition,expr_fpkm,od600,time_h
WT_LB_0,WT,LB,114.93,0.372,0
WT_LB_1,WT,LB,124.35,0.366,6
...
```

要求：一行一个观测，列名在首行，逗号或制表符分隔，编码 UTF-8（带 BOM 也可以）。

## 第一步：让 gaxis 读表

```bash
pixi run gaxis describe --data examples/demo/expr.tsv
```

你会看到每列的类型（numeric/categorical）、基数、单位提示，以及推荐的图型。

## 第二步：渲染

```bash
pixi run gaxis render \
  --data examples/demo/expr.tsv \
  --preset nature_microbiology \
  --out data/demo
```

```
figure: bar-65ca394dac
dir:    /…/data/demo/bar-65ca394dac
wrote:  /…/data/demo/bar-65ca394dac/bar-65ca394dac.pdf  (89 x 60 mm @600 dpi)
wrote:  /…/data/demo/bar-65ca394dac/bar-65ca394dac.png
lint:   clean
```

如果 lint 有 issue，命令仍会写文件，但退出码是 3（除非加 `--allow-lint-errors`）。
这是刻意的：图可以给你，问题不能藏。

## 第三步：读 manifest

```bash
pixi run gaxis manifest data/demo/bar-65ca394dac/manifest.json --json
```

关键字段：

| 字段 | 含义 |
|---|---|
| `figure_id` | `PIPELINE_VERSION + data.sha256 + spec` 的哈希前缀 |
| `data.sha256` | 输入表的内容 hash |
| `code_sha256` | 生成脚本的内容 hash |
| `spec` | 编码意图（图型、x/y/hue、预设、后端、几何） |
| `lint.issues[]` | 逐项检查与位置 |
| `outputs[]` | 每个产物的实测几何与 DPI |

## 第四步：改脚本

打开 `figure.py`，它就是一个普通的 matplotlib 脚本。比如把 y 轴标签改成带单位：

```python
ax.set_ylabel("expression (FPKM)")
```

然后直接运行它：

```bash
cd data/demo/bar-65ca394dac
python figure.py
```

!!! note "交付物不依赖 gaxis"
    脚本里没有 `import gaxis`。这是产品要求，不是巧合：它必须能在审稿人、合作者、三年后的你的机器上跑。

## 第五步：换后端和预设

```bash
# R / ggplot2
pixi run gaxis render --data examples/demo/expr.tsv --backend r --preset asm --out data/demo-r

# 换图型和编码
pixi run gaxis render --data examples/demo/expr.tsv \
  --chart line --x time_h --y od600 --hue genotype --preset isme
```

两个后端共享同一套数据分组与统计口径（`summarise()`），所以同一 spec 的 matplotlib 和 ggplot2
输出在结构上应当一致。

## 通过 MCP 做同样的事

宿主里等价调用：

```json
{"data_path": "/abs/expr.tsv", "preset": "nature_microbiology",
 "chart_type": "bar", "x": "genotype", "y": "expr_fpkm", "hue": "condition"}
```

返回 `figure_id`、`code_path`、`outputs[]`、`lint`、`manifest`。宿主应当把 `code_path` 一起展示给用户，
否则"图"就成了黑盒产物。

## 检查点

- [ ] `data/demo/<id>/figure.py` 不 import gaxis，单独运行成功；
- [ ] `manifest.json` 里 `data.sha256` 与 `code_sha256` 都非空；
- [ ] `lint: clean`（或你明确接受某条 issue）；
- [ ] 同一个 spec 用 `--backend r` 也能出 lint-clean 的图。

## 常见问题

**`unknown_column`**：`--x/--y/--hue` 的名字和表头不一致。先 `gaxis describe` 看可用列名。

**`not_numeric`**：heatmap/scatter/box 的 y 必须是数值列；检查是否有 `"NA"` 之外的非数字字符串。

**尺寸和预设不符**：`--width/--height` 覆盖了预设几何；投稿前用 `gaxis lint` 复核。
