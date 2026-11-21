# 03 模板适配：改数据不改代码

## 目标

复用一份**验证过的**绘图代码（模板），只把它绑定到你的数据上：数据路径、输出目录、分隔符、列映射。
不重新发明样式，也不让代码和数据偷偷错位。

## 前提：KB 里有模板

```bash
pixi run gaxis kb seed --preset asm --backend python
pixi run gaxis kb status
```

`kb seed` 会对每个（预设 × 图型 × 后端）真渲染一遍，lint 不过的不入库。模板页面是
`type: template`，带 `code_path`、`code_sha256`、`interface: full`。

幂等：重复执行只跳过未变项。

```bash
pixi run gaxis kb seed --preset asm --backend python
# templates: 0 written, 6 unchanged, 0 failed
```

## 第一次适配

```bash
pixi run gaxis adapt --data examples/demo/expr.tsv --preset asm --query "bar chart"
```

```
source:  kb_asset
asset:   template:asm-bar-python
figure:  bar-43e3d19d74
code:    /…/data/renders/bar-43e3d19d74/figure.py
wrote:   …/bar-43e3d19d74.pdf
lint: clean
```

`source: kb_asset` 表示代码来自知识库资产；`asset_ids` 记录具体模板；manifest 同样写入。

## 它到底改了什么

适配只重写人会改的常量，绘图代码原样保留：

| 常量 | Python | R |
|---|---|---|
| 数据路径 | `DATA_PATH = Path(...)` | `DATA_PATH <- "..."` |
| 输出目录 | `OUT_DIR = Path(...)` | `OUT_DIR <- "..."` |
| 文件名主干 | `STEM = "..."` | `STEM <- "..."` |
| 分隔符 | `DELIMITER = "\t"` | `SEP <- "\t"` |
| 编码意图 | `SPEC = {...}` | `SPEC <- list(...)` |

每一次替换都校验：模板结构不符（比如缺 `DATA_PATH`）会报 `adaptation_failed`，而不是跑错代码。

## 列名不同怎么办

`--query` 决定图型，但列名由你的数据决定。适配会把 `SPEC` 写成你的列名：

```bash
# 你的表：strain, group, value
pixi run gaxis adapt --data my.csv --preset asm --query "bar chart"
```

生成的 `figure.py` 里 `SPEC` 就是 `strain/group/value`，模板的统计与样式逻辑保持不变。
如果模板的图型不适合你的数据（比如要 heatmap 但只有两列数值），`infer_spec` 会选择能跑的编码，
产物会告诉你结果；不适配时会明确失败而不是静默。

## dry run 与代码审查

```bash
pixi run gaxis adapt --data my.csv --preset asm --query "bar chart" --dry-run
```

只写脚本和 manifest，不执行。适合先看 diff：

```bash
diff data/assets/templates/asm/bar-python/figure.py data/renders/<id>/figure.py
```

你会看到只有常量块不同。

## 换后端

```bash
pixi run gaxis adapt --data my.csv --preset asm --backend r --query "bar chart"
```

R 模板同样只改绑定，绘图部分是 ggplot2。

## 模板缺失时会发生什么

```bash
pixi run gaxis adapt --data my.csv --preset nature --query "bar chart"
```

```
source:  builtin_templates
fallback: no verified template for preset=nature chart=bar backend=python; run `gaxis kb seed`
```

这是**显式降级**：仍然出图，但明确告诉你没有用上 KB 模板。补齐：

```bash
pixi run gaxis kb seed --preset nature
```

## 检查点

- [ ] `source: kb_asset`，`asset_ids` 非空；
- [ ] 生成脚本只改常量块，绘图代码与模板一致；
- [ ] `manifest.asset_ids` 与终端一致；
- [ ] `data/kb/selections.jsonl` 有 `action: adapt` 记录。

## 常见问题

**`no verified template ... run gaxis kb seed`**：该预设/图型/后端没有模板。先 seed。

**`adaptation_failed: template is missing ...`**：资产不是 gaxis 生成的模板（例如手工放进 KB 的脚本）。
用 `kb adopt` 走论文代码通道（下一节），或 `kb seed --force` 重建成模板。

**适配后图不对**：先 `diff` 模板与产物；再检查 `SPEC` 里的列名是否真的存在。适配不理解业务语义，
它只保证绑定正确。
