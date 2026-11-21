# 期刊预设与出版 lint

预设即数据:`src/gaxis/style/journal_presets/*.toml`。新增期刊绝不应需要改动 `render/templates/*.tpl`(ADR-16)。

## 1. 可用预设(微生物学优先)

| 预设 | 单栏 | 双栏 | 基础字号 | DPI | 目标期刊 |
|---|---|---|---|---|---|
| `default` | 120 × 80 mm | 180 × 120 mm | 9 pt | 600 | 未指定期刊时的安全回退 |
| `nature` | 89 × 60 mm | 183 × 120 mm | 7 pt | 600 | Nature 系列期刊 |
| `nature_microbiology` | 89 × 60 mm | 183 × 120 mm | 7 pt | 600 | Nature Microbiology |
| `asm` | 84 × 62 mm | 175 × 120 mm | 8 pt | 600 | mBio、AEM、Microbiology Spectrum |
| `isme` | 90 × 65 mm | 180 × 125 mm | 7.5 pt | 600 | ISME Journal |
| `cell_host_microbe` | 85 × 60 mm | 174 × 110 mm | 7 pt | 600 | Cell Host & Microbe |
| `microbial_genomics` | 90 × 65 mm | 190 × 130 mm | 8 pt | 600 | Microbial Genomics(Microbiology Society) |

可在运行时查看:`pixi run gaxis presets` / `--json`。

单栏与双栏:若 `width_mm` 超过单栏宽度 15% 以上,则自动采用双栏高度(`style/presets.py::resolve_size`)。可通过 `--width/--height` 显式覆盖。

## 2. 字段

| 键 | 含义 |
|---|---|
| `width_single_mm`, `width_double_mm` | 栏几何尺寸,即审稿人会核对的那些数字 |
| `height_mm`, `height_double_mm` | 各宽度档位的默认高度 |
| `base_font_pt` | 刻度、图例文字、注释标注 |
| `label_font_pt` | 坐标轴标签 |
| `title_font_pt` | 标题 / 分图标题 |
| `line_width_pt`, `spine_width_pt`, `marker_size_pt` | 线条粗细;期刊的最低要求通常在 0.25–0.5 pt 左右 |
| `dpi` | 栅格导出的 DPI(不影响矢量输出) |
| `font_family` | 有序回退字体链,基于已安装字体进行解析 |
| `palette` | 默认调色板名称;除非期刊另有规定,否则为 `okabe_ito` |
| `legend_frame`, `grid` | 图表冗余元素(chart junk)开关 |
| `spines` | 保留哪些坐标轴脊线(`["left","bottom"]` 为默认的极简边框) |
| `vector_required` | 为 true 时,仅有栅格输出的渲染会被 lint 判为**错误** |

字体策略:matplotlib 通过 `font_manager` 解析字体链;ggplot2 将解析出的字族传给 `theme_classic(base_family=...)`。在这台工作站上,`Arial` 会解析为 `Liberation Sans`(度量兼容)。字体回退绝不静默进行:lint `L005` 会报告字体不匹配,且清单(manifest)会在 `style.font` 下记录解析出的字体。

## 3. 后端映射

| 预设字段 | matplotlib(`style/rc.py`)| ggplot2(`render/templates/r_header.tpl`)| 
|---|---|---|
| `base_font_pt` | `font.size`、刻度字号、图例字号 | `theme_classic(base_size=)`、`axis.text`、`legend.text` |
| `label_font_pt` | `axes.labelsize` | `axis.title` |
| `title_font_pt` | `axes.titlesize` | `plot.title` |
| `spine_width_pt` | `axes.linewidth`、刻度线宽 | `axis.line`、`axis.ticks` |
| `line_width_pt` | `lines.linewidth` | `geom_line(linewidth=)` |
| `marker_size_pt` | `lines.markersize` | `geom_point(size = pt * 0.3528)`(ggplot2 的尺寸单位为 mm) |
| `spines`, `grid`, `legend_frame` | rcParams | `theme()` 元素 |
| 宽度/高度 | `figure.figsize`(以英寸为单位)| `ggsave(units = "mm")` |
| 矢量安全 | `pdf.fonttype = 42`、`svg.fonttype = "none"` | `cairo_pdf`、`svglite` |

两种后端写入相同的聚合统计(均值 + 标准差,或给定 `yerr` 列的均值),因此从 Python 切换到 R 后的图形在数值上可比,而不只是看起来相似。

## 4. 输出安全

- `savefig.bbox="tight"`、`pad_inches=0.01`(matplotlib)以及 `ggsave` 的边距,可确保导出几何尺寸与标称宽度相差仅百分之几;lint `L006` 容忍 3%(信息级),超过 15% 则判定失败。
- PNG/TIFF 以预设 DPI 写出,并使用不透明的白色背景。
- PDF 字体嵌入为 TrueType(Type 42)/ cairo;Type 3 属于 lint 错误。

## 5. Lint 规则

| 代码 | 严重级别 | 含义 | 典型修复 |
|---|---|---|---|
| L001 | 错误 | 输出文件缺失或为空 | 检查 `formats`,检查 `render.log` |
| L002 | 错误 | 需要矢量输出但未生成 | 添加 `pdf` 或 `svg` |
| L003 | 错误 / 信息 | 栅格 DPI < 300(错误)或 < 预设 DPI(信息)| 提高 `--dpi` |
| L004 | 错误 | PDF 含有 Type 3 字体 | 使用 `pdf.fonttype=42` / `cairo_pdf` |
| L005 | 警告 | 字体回退与预设不符 | 安装该期刊字体,或接受 Liberation Sans |
| L006 | 错误 / 信息 | 几何尺寸偏差超过 15% / 超过 3% | 设置 `--width/--height`,避免手动修改 `bbox` |
| L007 | 警告 | 调色板对色盲不友好 | 改用 `okabe_ito` / `viridis` |
| L008 | 警告 | SVG 文本层中未找到标题/坐标轴标签 | 检查标签,或导出 SVG(而不仅仅是 PDF) |
| L009 | 警告 | 文件小于 2 KB | 很可能是空白图形 |

可对已完成的文件独立运行(任意工具、任意语言):

```bash
pixi run gaxis lint figure.pdf figure.svg --preset nature_microbiology
pixi run gaxis lint figure.png --preset asm --width 84 --height 62 --json
```

只要存在任何错误级问题,退出码即为 `3`,因此可用于投稿 CI 的门禁。

## 6. 新增期刊预设

1. 创建 `src/gaxis/style/journal_presets/<name>.toml`,填入上述字段。
2. 运行 `pixi run gaxis presets` —— 应无需改动任何代码。
3. 在两种后端中各渲染一次,并确认输出 `lint: clean`:
   ```bash
   pixi run gaxis render --data examples/demo/expr.tsv --preset <name> --out data/check
   pixi run gaxis render --data examples/demo/expr.tsv --preset <name> --backend r --out data/check-r
   ```
4. 在 TOML 的 `description` 中记录这些数字的来源(作者指南 URL + 访问日期)—— 面向审稿人的数字若没有出处,会遭到质疑。

## 7. 调色板

| 名称 | 色盲友好 | 备注 |
|---|---|---|
| `okabe_ito` | 是 | 默认;Nature 推荐用于色觉障碍(CVD)无障碍 |
| `viridis` | 是 | 感知均匀,印刷安全 |
| `greys` | 是 | 单色印刷/复印 |
| `npg` | 否 | Nature Publishing Group 调色板,高饱和度 |
| `set2` | 否 | ColorBrewer Set2 |

允许使用对 CVD 不安全的调色板,但会予以标记(`L007`),从而让这种取舍是显式的,而非无意的。
