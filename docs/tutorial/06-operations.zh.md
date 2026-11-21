# 06 运维：队列、定时与自愈

## 目标

让知识库自动增长，同时保证"失败可见、进度可恢复、证据可校验"。

这一节的所有操作都是幂等的：中断、重跑、并发触发都不会重复完成的工作。

## 1. 检查点队列

```bash
# 入库作业
pixi run gaxis ops enqueue 10.1099/mgen.0.000001 paper.pdf --mode full

# 复现作业（source 是 paper id）
pixi run gaxis ops enqueue --kind reproduce pdf-0883b2ad

pixi run gaxis ops run --limit 5 --retries 2
pixi run gaxis ops status
```

队列存在 `data/ops/queue.db`（SQLite），每行是一个 source：

| 字段 | 含义 |
|---|---|
| `status` | `pending` / `running` / `done` / `failed` |
| `kind` | `ingest` / `reproduce` |
| `attempts` | 已尝试次数 |
| `last_error` | 最后一次失败原因（截断 500 字符） |
| `manifest_ids` | 该 source 产生的 manifest，证据 |
| `updated_at` | 检查点时间 |

行为约定：

- **每个 source 是独立检查点**：崩了重启只续跑未完成的；
- **`done` 不重跑**（按 source 字符串去重，用规范 DOI/paper id）；
- **只对暂时性失败重试**（`resolution_failed`、`download_failed`、`pdf_unreadable`）；
- **永久失败**（`unrecognised_source` 等）停在 `failed`，需要显式 `status --reset`。

## 2. 停滞回收与心跳

`ops run` 每次开始时会：

- 把停留超过 `--stall-minutes`（默认 30）的 `running` 作业回收为 `pending`——进程被杀后的自愈；
- 结束后写 `data/ops/heartbeat.json`：

```json
{"finished_at": "2026-11-21T12:40:03+00:00", "duration_s": 42.1,
 "processed": ["10.1099/mgen.0.000001"], "failed": [],
 "reclaimed": 0, "queue": {"done": 1}}
```

`ops status` 会显示最后一次运行。

## 3. 深度校验：证据还在不在

```bash
pixi run gaxis ops verify
```

它检查每个 `done` 作业的 `manifest_ids` 是否仍然存在且可解析；证据丢了（清过 `data/`、恢复失败）
就回队并写明原因：

```
checked 1 done job(s); missing 0 manifest(s); requeued 0
```

!!! warning "`done` 不等于完成"
    一个没有 manifest 的 `done` 是假的状态。`verify` 的职责就是纠正它，而不是掩盖。

## 4. 定时运行

队列没有常驻守护进程，用 systemd user timer 即可：

```ini
# ~/.config/systemd/user/gaxis.timer
[Unit]
Description=gaxis 每 6 小时跑一次入库队列

[Timer]
OnBootSec=15min
OnUnitActiveSec=6h
Persistent=true

[Install]
WantedBy=timers.target
```

```ini
# ~/.config/systemd/user/gaxis.service
[Unit]
Description=gaxis ingestion queue

[Service]
Type=oneshot
WorkingDirectory=%h/repos/github/gaxis
ExecStart=%h/.pixi/bin/pixi run gaxis ops run --limit 10 --retries 2
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now gaxis.timer
systemctl --user list-timers gaxis.timer
```

`Persistent=true` 让关机错过的运行在开机后补一次；`--limit` 控制单次时长，避免 timer 叠加。

## 5. 健康检查（只读）

```bash
pixi run gaxis health
pixi run gaxis-mcp --transport http --port 8770   # 宿主侧可轮询 health 工具
```

`health` 不渲染、不下载、不加锁、不写文件，可以放心用于存活探针与时钟偏差检查。

## 6. 环境变量速查

| 变量 | 作用 |
|---|---|
| `GAXIS_DATA_DIR` | 数据根目录（默认 `./data`） |
| `GAXIS_CONFIG` | 配置文件路径 |
| `GAXIS_SANDBOX_BACKEND` | `podman` 或 `local` |
| `GAXIS_KB_ENABLED` | 关掉知识库（测试/离线） |
| `GAXIS_GBRAIN_HOME` | gbrain 数据目录 |
| `GAXIS_MCP_TOKEN` | MCP server 的 Bearer token（必需） |

完整列表见[配置参考](../reference/configuration.zh.md)。

## 7. 日志与排错

- 渲染：`<figure-dir>/render.log`（stdout/stderr/exit code）；
- 复现：`data/repro/<asset>/<sha8>/reproduction.json`（分级、相似度分解、沙箱报告）；
- 队列：`data/ops/queue.db`（可用 `sqlite3` 直查）；
- 心跳：`data/ops/heartbeat.json`；
- 选择反馈：`data/kb/selections.jsonl`。

## 检查点

- [ ] `ops enqueue` 同一 source 两次，第二次返回 `0 new … already known`；
- [ ] 杀掉一个运行中的 `ops run` 后，下一次运行会 `reclaimed 1` 并继续；
- [ ] `ops verify` 在删掉一个 manifest 后能把它回队；
- [ ] `heartbeat.json` 的 `queue` 计数与 `ops status` 一致。

## 常见问题

**timer 一直不触发**：`systemctl --user status gaxis.timer` 看 `NextElapse`；user 需要 `loginctl enable-linger` 才能在未登录时运行。

**队列卡在 running 但进程已不在**：下次 `ops run` 会自动回收；急用就 `ops status --reset <source>`。

**gbrain 锁超时**：`gbrain embed` 或另一个 gbrain 进程持有数据库锁。等它结束，不要删锁文件。
