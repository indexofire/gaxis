# 参与开发

仓库根目录的 `AGENTS.md` 是完整的开发规则；这里只列最常用的。

## 环境

```bash
pixi install
pixi run check      # 提交前必须绿
pixi run fmt
```

## 五条硬规则（违反需要先写决策）

1. **工具契约冻结**：10 个 MCP 工具（v2.1）。改名字/输入/输出要升版本、刷新
   `tests/contract_snapshot.json`（`pixi run python scripts/freeze_contract.py`）、更新
   `docs/mcp-tools.md` 与 `docs/service-flows.md`。
2. **core 不 import 宿主 SDK**：`models/spec/style/render/exec/service.py` 里没有 bacmap/Pi/DSH。
3. **宿主适配器薄**：≤150 行，无业务逻辑，互不 import。
4. **生成的代码不 import gaxis**：`figure.py` / `figure.R` 必须能独立运行。
5. **每次渲染写 manifest**：`data.sha256`、`code_sha256`、输出、lint，一个不能少。

其他关键约定：

- 双后端对等：任何图型能力在 matplotlib 和 ggplot2 同时提供，否则不上；
- 无静默降级：缺字体、缺预设、回退后端、跳过沙箱，必须出现在 lint 或 manifest；
- `health` 只读；
- 每个工具声明 `data_class`；
- 渲染路径里不调用 LLM；
- 论文代码只在沙箱里跑，克隆的代码在 ingest 阶段永不执行。

## 加一个功能

1. 先看 `DESIGN.md` 与 `docs/service-flows.md` 的契约；
2. 数据模型放 `models/`（跨模块不允许裸 dict）；
3. 失败用 `GaxisError(code, message, hint)`，code 是稳定字符串；
4. 新增行为要有测试：渲染类端到端，推断/lint 类单元；
5. Python 与 R 都要有输出（新图型）；
6. 文档跟着改：本页、`docs/mcp-tools.md`、`CHANGELOG.md`。

## 改契约

```bash
# 1. 改模型/工具签名与版本号
# 2. 刷新快照
pixi run python scripts/freeze_contract.py
# 3. 更新 docs/mcp-tools.md 的对应小节与版本表
# 4. 写 CHANGELOG
pixi run check
```

## 文档

本站是双语文档，由 MkDocs Material + `mkdocs-static-i18n`（**suffix** 模式）构建：

```
docs/page.md        英文（默认）
docs/page.zh.md     简体中文
```

```bash
pixi run docs-serve      # 预览：http://127.0.0.1:8000/gaxis/（英文）与 /gaxis/zh/（中文）
pixi run docs-build      # strict 构建：链接/导航/翻译缺失都会失败
```

新增或修改页面时：

1. **同时**提供 `page.md` 与 `page.zh.md`，不要让某一种语言静默回退；
2. 在 `mkdocs.yml` 的 `nav` 中登记页面，并把标题加入
   `plugins.i18n.languages[zh].nav_translations`；
3. `.zh.md` 页面里的链接指向 `other.zh.md`；英文页面里的链接指向 `other.md`；
4. 图片放在 `docs/assets/`，统一用站点的绝对路径 `/gaxis/assets/…` 引用——中英文与本地预览
   都能解析（站点部署在 `/gaxis/` 下）；
5. 文档里的命令必须能直接执行——不要写不存在的参数。
