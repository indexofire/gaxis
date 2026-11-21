# 快速开始

目标：10 分钟内从零到一张带脚本和 manifest 的期刊图，并知道怎么验证结果。

## 1. 前置条件

| 依赖 | 用途 | 是否必需 |
|---|---|---|
| [pixi](https://pixi.sh) | 提供 Python 3.12、matplotlib、R + ggplot2 | 必需 |
| rootless podman | 论文代码沙箱（`gaxis reproduce`） | 复现时需要 |
| gbrain + bun | 本地知识库与检索 | 选图/复现/入库时需要 |
| 网络 | 论文下载、仓库克隆、逐篇镜像构建 | 仅论文流程需要 |

```bash
pixi install
pixi run gaxis health
```

`health` 是只读探针，报告后端、预设、各阶段就绪情况：

```json
{"ok": true, "version": "0.1.0", "python_backend": true, "r_backend": true,
 "presets": ["default", "nature", …], "stages": {"python": "ready", "r": "ready"}}
```

## 2. 配置（可选）

gaxis 的默认值即可工作。要改预设默认值、数据目录或知识库开关时，把 `gaxis.example.toml` 复制成 `gaxis.toml`：

```bash
cp gaxis.example.toml gaxis.toml
pixi run gaxis config          # 查看生效配置（文件 + 环境变量覆盖）
```

配置优先级：`--config` > `$GAXIS_CONFIG` > `./gaxis.toml` > `~/.config/gaxis/config.toml` > 默认值。
完整字段见[配置参考](reference/configuration.zh.md)。

## 3. 第一张图

```bash
pixi run gaxis describe --data examples/demo/expr.tsv
```

输出列类型、基数、单位提示和推荐编码。然后：

```bash
pixi run gaxis render \
  --data examples/demo/expr.tsv \
  --preset nature_microbiology \
  --out data/demo
```

```
figure: bar-65ca394dac
dir:    /…/data/demo/bar-65ca394dac
figure.py   bar-65ca394dac.pdf   bar-65ca394dac.png   manifest.json
lint: clean
```

`figure.py` 里是完整、可直接运行的 matplotlib 代码：改标签、改颜色、改统计口径都行，不需要 gaxis。

## 4. 换后端与图表类型

```bash
# ggplot2 后端
pixi run gaxis render --data examples/demo/expr.tsv --backend r --preset asm --out data/demo-r

# 指定图型与编码
pixi run gaxis render --data examples/demo/expr.tsv \
  --chart line --x time_h --y od600 --hue genotype --preset isme
```

6 种图型：`bar`、`stacked_bar`、`line`、`scatter`、`box`、`heatmap`。
7 个预设见[期刊预设](presets.zh.md)。

## 5. 检查交付质量

```bash
pixi run gaxis lint data/demo/<figure-id>/<figure-id>.pdf --preset nature_microbiology
pixi run gaxis manifest data/demo/<figure-id>/manifest.json --json
```

lint 规则覆盖矢量输出、DPI、Type3 字体、几何尺寸、字体回退、色盲配色和缺失标签（L001–L009）。
manifest 里的 `data.sha256` 和 `code_sha256` 是证据，不是装饰。

## 6. 打开知识库（选图与复现的前提）

```bash
pixi run gbrain-install     # 首次：vendor gbrain + 固定 bun
pixi run gbrain-init        # 在 ${XDG_DATA_HOME:-~/.local/share}/gaxis/gbrain 建库
pixi run gaxis kb status
pixi run gaxis kb seed      # 84 个验证模板（可离线，约 2–3 分钟）
```

之后：

```bash
pixi run gaxis kb search "rarefaction curve" --k 3
pixi run gaxis kb search --schema examples/demo/expr.tsv --sheet
```

## 7. 启动 MCP server（宿主接入）

```bash
export GAXIS_MCP_TOKEN="$(openssl rand -hex 24)"
pixi run gaxis-mcp --transport http --port 8770
```

没有 token 会拒绝启动；`stdio` 只用于本地调试。工具清单与逐项契约见 [MCP 工具契约](mcp-tools.zh.md)。

## 下一步

- 跟着[教程](tutorial/index.zh.md)把选图、适配、复现、拼版、运维各做一遍；
- 或直接看[命令行参考](reference/cli.zh.md)。
