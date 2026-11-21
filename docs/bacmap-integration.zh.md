# bacmap 集成

gaxis 被设计为 **bacmap 研究工作流中的单一工具表面**，同时也是一款独立工具。本文档是 bacmap 一侧的契约；参考适配器位于 `integrations/bacmap_upstream_gaxis.py`(仓库根目录，不属于本站点)。

## 1. 拓扑

```
bacmap MCP server ──(upstream MCP client)──► gaxis MCP server (Streamable HTTP)
      │                                            │
      └─ LLM sees bacmap_chart_* tools             └─ figure + script + manifest
```

- gaxis 作为独立进程运行(ADR-01/02)。bacmap 从不导入 gaxis 的内部实现。
- 适配器很薄：只做映射、命名与门控。不含论文逻辑、图表逻辑，也不做缓存。
- 启动顺序无关紧要：gaxis 不可达时只会返回 JSON 错误，绝不会导致整轮交互崩溃。

## 2. 启动 gaxis

```bash
export GAXIS_MCP_TOKEN="$(openssl rand -hex 24)"
gaxis-mcp --transport http --host 127.0.0.1 --port 8770
# client endpoint: http://127.0.0.1:8770/mcp, Authorization: Bearer <token>
```

没有令牌时 HTTP 传输会拒绝启动(fail-closed,与 bacmap 的策略相同)。`--transport stdio` 仅用于本地调试。

## 3. 将适配器接入 bacmap

将参考文件复制到 `bacmap/src/bacmap/interfaces/mcp/upstream/gaxis.py`,然后在组装服务器的地方注册它：

```python
from bacmap.interfaces.mcp.upstream.gaxis import GaxisUpstream

upstream = GaxisUpstream(
    url=cfg.gaxis.url,  # default http://127.0.0.1:8770/mcp
    token=os.environ["GAXIS_MCP_TOKEN"],
    max_data_class=profile.max_data_class,  # cloud profile → "D1"
)
upstream.register(server)  # returns the registered names
```

`register()` 是增量的，且每次调用都是幂等的：每个可见工具都会变为 `bacmap_chart_<gaxis tool name>`,并带有一个 `params` 输入模型，与 bacmap 现有的 legacy 工具约定一致(`{"params": {...}}`,schema 位于 `$defs`)。

## 4. 数据类别门控(这个适配器存在的原因)

gaxis 工具声明了 `data_class`:

| gaxis 工具 | 类别 | 涉及内容 |
|---|---|---|
| `health` | D1 | 无 |
| `search_chart_assets` | D1 | 论文语料库 |
| `get_chart_manifest` | D1 | 论文语料库 |
| `reproduce_chart_code` | D1 | 沙箱中的论文代码 |
| `describe_data_schema` | D3 | 本地用户数据表 |
| `render_chart_from_data` | D3 | 本地用户数据表 |
| `adapt_chart_code` | D3 | 本地用户数据表 |

在 bacmap 的 `cloud` 配置(上限 D1)下的后果：四个 D3 工具**根本不会被注册**，因此模型根本看不到它们，直接调用也会在离开进程之前被拒绝。在 `local-trusted`(D4)下，七个工具全部出现。

门控被刻意做了双重设计：注册时(可见性)和调用时(纵深防御)。两者都以 JSON 错误的形式 fail closed,与 bacmap 自身的 `_register_legacy_tool` 模式一致。

## 5. 结果形态

bacmap 的处理器返回 JSON 字符串；gaxis 返回结构化内容。适配器会将其字符串化，并保留 gaxis 的错误约定：

```json
{"error": "...", "code": "unknown_column", "message": "...", "hint": "available columns: [...]"}
```

`code` 是稳定的内核错误码(`data_not_found`、`unknown_column`、`not_numeric`、`missing_x`、`missing_y`、`render_failed`、`bad_parameter`),因此 bacmap 无需解析自然语言即可将其映射到 `suggested_fix`/`recovery_commands`。

## 6. bacmap 应当与不应当如何使用它

**应当**

- 先使用 `describe_data_schema`,在目标期刊已知时再用显式 `preset` 调用 `render_chart_from_data`(`nature_microbiology`、`asm`、`isme`、`cell_host_microbe`、`microbial_genomics`)。
- 把返回的 `code_path` + `manifest_path` 视为交付物：manifest 携带 `data.sha256` 与 `code_sha256`,正是这些内容使图表在论文草稿中可审计。
- 将 `lint.issues` 呈现给用户，而不是默默接受警告。
- 在长时间批处理之前调用 `health` 以确认 R 后端已安装(ggplot2 图表需要它)。

**不应当**

- 在 bacmap 中缓存复现结果；缓存与加权由知识库(M3/M4)负责。
- 通过在运行时放宽上限，把 D3/D4 数据经 `cloud` 配置传递——该配置在启动时设定是有原因的。
- 在 bacmap 中重新实现规格推断：当模型已了解生物学含义时传入显式的 `x`/`y`/`hue`,只有在不了解时才让 gaxis 去推断。

## 7. 论文侧工具的当前行为

在 M1–M4 落地之前，论文侧会选择降级而不是失败：

| 工具 | 当前 | 之后 |
|---|---|---|
| `search_chart_assets` | `degraded: true`、空列表、消息 | M3:基于 `paper-kb` 的向量 + 图检索 |
| `get_chart_manifest` | `found: false` | M1: ChartReproManifest |
| `reproduce_chart_code` | `not_implemented: true`、`run_status: "skipped"` | M2:podman 沙箱 + L1/L2/L3 |
| `adapt_chart_code` | 可用，`source: "builtin_templates"`,`fallback_reason` 说明原因 | M4:`source: "kb_asset"` 附带 `asset_ids` |

这是有意为之：宿主今天就可以接入全部十个工具，并随着时间推移获得更好的结果，而无需改动自身代码。

## 8. 故障模式及其表现

| 症状 | 原因 | 处理方式 |
|---|---|---|
| `{"error": "gaxis unreachable at ..."}` | 服务器未运行 / 端口错误 | 启动 gaxis;适配器会预检 TCP,因此能立即发现 |
| 连接时收到 HTTP 401 | 令牌缺失或不匹配 | 检查两侧的 `GAXIS_MCP_TOKEN` |
| `{"error": "... above the profile ceiling ..."}` | 在 D1 配置下调用 D3 工具 | 使用 `local-trusted`,或不要请求本地数据图表 |
| `code: "render_failed"` + `hint`(stderr 最后几行) | 生成的脚本出错 | 完整日志位于 `<figure dir>/render.log` |
| `code: "not_numeric"` | `y` 指向了分类型列 | 调用 `describe_data_schema` 并选择数值列 |
| `code: "unknown_column"` | 拼写错误或 schema 过期 | `hint` 会列出可用列 |

## 9. 验证

gaxis 通过运行真实流程的测试来确保适配器不出差错：

```bash
pixi run pytest -q tests/test_mcp.py tests/test_bacmap_upstream.py
```

这些测试会在回环地址上启动真实的 Streamable-HTTP 服务器，强制鉴权，通过 MCP 渲染图表，并断言配置门控、命名、JSON 字符串结果与错误映射。如果你修改了适配器，这些测试必须保持通过。
