# 跨宿主编排：交接包与能力等级（v2.6.0）

> `{SKILL}` = 本 skill 安装目录。所有命令在**用户工作区**执行。
> 本文件是规范；实现见 `{SKILL}/scripts/host_handoff.py`。

## 1. 为什么

五角色接力原先靠提示词描述「怎么派活」——「用后台 subagent 调用下游角色」「用 read 工具读取」。
这类写法把编排绑死在特定宿主上：Claude Code / Codex / Cursor / WorkBuddy / Trae / DSH
对子代理、工具名、后台任务的支持各不相同，没有 subagent 的宿主会直接断在第一步。

**门禁层本来就是宿主无关的**（纯 Python 回执链 + 字节绑定，不依赖任何宿主 hook）。
v2.6.0 把编排层也变成宿主无关：让「派活」从提示词变成**数据**。

## 2. 交接包契约

`中间产物/{batch}/_handoff/{stage}.json`，由 `host_handoff.py build` 生成：

| 字段 | 含义 |
|---|---|
| `owner` / `role_skill` / `prompt_ref` | 该阶段由谁执行、读哪份手册与提示词 |
| `inputs[]` | `path` + `sha256` + `exists` + `read`（`full`/`by-id`） + `selector` |
| `outputs[]` | 该阶段必须落盘的产物路径 |
| `preflight` | 派活前可独立执行的回执审计命令（`a2` 无前置 → `null`） |
| `gate` | 该阶段的门禁命令，恒指向 `gate_run.py` |
| `done[]` | 完成判据（产物可解析 + 门禁 exit 0） |
| `report_format` | 执行方回报固定三行，不写分析散文 |
| `write_scope` / `parallel_safe` | 写范围；`question_bank` 恒 `parallel_safe=false` |
| `supported_levels` | `L2 / L1 / L0` |
| `inputs_fingerprint` / `rebuild_if` | 产物字节变了包即过期，必须重跑 `build` |

三条硬纪律：

1. **包里不含任何宿主工具名**（subagent / read 工具 / bash / PowerShell …），只描述数据与命令。
2. **哈希复用 `gate_ledger.file_sha256`**，与回执链同一真相源；包内容无时间戳，重复 build 产出同一字节。
3. **`write_scope=question_bank` 的阶段任何宿主都不许并发写**（Cognition 原则 2：写操作携带隐式决策，
   并行写会互相覆盖）。并行只给只读阶段与其它批次的独立任务。

## 3. 三档消费方式（同一份包）

| 档 | 典型宿主 | 怎么做 |
|---|---|---|
| **L2** | 有隔离子代理的宿主（DSH、WorkBuddy、Claude Code 等） | 主会话读包 → 派生子任务，把包字段当任务描述；`parallel_safe=true` 的阶段可并行 |
| **L1** | 只有单会话的 IDE Agent（Trae、Cursor 等） | 同会话按包顺序执行；**每阶段开始重读 `_ctx.md` 复位上下文**；按 `inputs[].read` 限定读入范围，不整库读 |
| **L0** | 无 Agent / 人工接力 | `host_handoff.py brief --batch X --stage S` 打印人读交接单，照命令执行 |

三档消费同一份 JSON，产物字节与门禁回执一致——**宿主只回答「能不能并行派生」，其余全部照包执行**。

## 4. 命令

```bash
# 生成下一阶段的交接包（幂等；内容无时间戳）
python {SKILL}/scripts/host_handoff.py build --batch batchNNN --stage a3

# 人读交接单（会检查包是否过期：exit 3 = 产物 sha 变了，重跑 build）
python {SKILL}/scripts/host_handoff.py brief --batch batchNNN --stage a3

# 回执审计（派活前确认上游链成立）
python {SKILL}/scripts/gate_audit.py --batch batchNNN

# 阶段门禁（唯一执行面，内建 preflight，PASS 才写回执）
python {SKILL}/scripts/gate_run.py --batch batchNNN --stage a3
```

## 5. 边界

- 交接包**不是证据**：它只是执行指令，不进回执链；证据仍由 `gate_run.py` + `gate_ledger.py` 产出。
- 包**不追溯历史批次**：只在下次 `build` / 门禁 PASS 后落盘；无包时 `brief` 会提示先跑 `build`。
- 本工具**不修改** `gate_run.py` / `gate_ledger.py`，也不写回执、不跑门禁。
- 主仓 MedAgentWork 的等价实现是 `scripts/batch_driver.py`（子命令 `check` / `brief`）与
  `scripts/host_bootstrap.py`（入口桩的 `level=` 声明）；两者 bundle schema 均为 `1.0`，
  字段口径一致，便于对照。
