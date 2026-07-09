# Mini Claude Code ZH

一个从零构建的中文 Agent 运行时项目，目标是把模型调用、工具执行、权限控制、任务系统、长期记忆、后台任务、定时调度、多 Agent 协作、自治任务认领和 worktree 隔离统一到一套清晰的 Python 架构中。

项目以 `agent_loop.py` 为入口，围绕“模型产生工具调用 → 权限和 Hook 检查 → 工具执行 → 结果回写上下文 → 继续推理”的主循环逐步扩展能力。

## 核心能力

- Agent Loop：支持模型多轮调用工具，直到产出最终回答。
- 工具系统：内置 `bash`、`read_file`、`write_file`、`edit_file` 等基础工具。
- 权限控制：通过 allow/deny、危险命令拦截和用户审批保护工具执行。
- Hook 机制：在会话启动、模型调用前后、工具调用前后、停止阶段挂载扩展逻辑。
- 计划管理：使用 `todo` 维护当前会话的短期执行计划。
- 子 Agent：支持将复杂子任务交给独立上下文执行。
- 技能加载：按需加载 `skills/` 中的技能说明，避免一次性塞满上下文。
- 上下文压缩：对大工具输出和长历史做落盘、裁剪和摘要。
- 长期记忆：把可复用信息保存到 `.memory/`，并在后续会话中按需注入。
- 系统提示词组装：运行时按模块动态生成 system prompt。
- 错误恢复：处理临时错误、上下文超限和输出截断。
- 持久任务系统：使用 `.tasks/` 保存任务图，支持依赖、认领、完成和解锁。
- 后台任务：慢命令可放到后台执行，Agent 继续处理其他工作。
- 定时调度器：按 cron 表达式生产工作，调度和执行解耦。
- Agent Teams：Lead Agent 可启动 teammate 线程，通过文件 inbox 协作。
- Team Protocols：支持关闭请求、计划审批、请求状态追踪等团队协议。
- Autonomous Agents：teammate 空闲时自动扫描任务看板并认领 ready task。
- Worktree Isolation：为任务绑定独立 git worktree，让并行 teammate 各自工作。

## 项目结构

```text
.
├── agent_loop.py                 # 主入口和 Agent Loop
├── model_client.py               # OpenAI 兼容客户端创建
├── configs/                      # 各模块配置
├── handlers/                     # 工具 handler
├── hooks/                        # Hook 管理和内置 Hook
├── managers/                     # 有状态能力管理器
├── prompts/                      # 系统提示词和规则片段
├── skills/                       # 可按需加载的技能
├── state/                        # 数据结构定义
├── subagents/                    # 子 Agent 和 teammate 循环
├── tools/                        # 工具底层实现
├── tools_configs/                # 工具 schema
├── utils/                        # 配置、路径沙箱、日志、消息规范化等工具
├── docs/                         # 分阶段设计与实现说明
├── .tasks/                       # 持久任务运行态
├── .team/                        # 团队消息和 teammate 运行态
├── .runtime-tasks/               # 后台任务和定时任务运行态
├── .memory/                      # 长期记忆运行态
├── .worktrees/                   # worktree 索引和事件流
└── .transcripts/                 # 压缩前会话记录
```

## 快速开始

安装依赖：

```bash
pip install -r requirements.txt
```

创建 `.env`，填写 OpenAI 兼容接口配置：

```env
ANTHROPIC_BASE_URL=你的模型服务地址
ANTHROPIC_AUTH_TOKEN=你的 API Key
MODEL_ID=你的模型 ID
```

启动：

```bash
python agent_loop.py
```

当前入口中的 `question` 是便于本地验证的测试问题。开发或测试不同模块时，可以直接修改 `agent_loop.py` 里的 `question` 文本。

## 配置文件

主要配置位于 `configs/`：

| 文件 | 说明 |
|---|---|
| `permission_config.yml` | 工具 allow/deny、危险命令和审批策略 |
| `hooks_config.yml` | 外部 Hook 配置 |
| `todo_config.yml` | 计划提醒策略 |
| `subagent_config.yml` | 子 Agent 配置 |
| `skill_config.yml` | 技能目录和加载策略 |
| `compact_config.yml` | 上下文压缩策略 |
| `memory_config.yml` | 长期记忆配置 |
| `prompt_config.yml` | 系统提示词组装配置 |
| `recovery_config.yml` | 错误恢复配置 |
| `task_config.yml` | 持久任务系统配置 |
| `background_config.yml` | 后台任务配置 |
| `cron_config.yml` | 定时调度器配置 |
| `team_config.yml` | Agent Teams、协议和自治 Agent 配置 |
| `worktree_config.yml` | Worktree Isolation 配置 |

## 工具能力概览

项目中的工具按模块组合到 `BASE_TOOLS`：

- 基础工具：`bash`、`read_file`、`write_file`、`edit_file`
- 计划工具：`todo`
- 子 Agent：`task`
- 技能工具：`load_skill`
- 压缩工具：`compact`
- 记忆工具：`save_memory`、`forget_memory`
- 任务工具：`task_create`、`task_list`、`task_get`、`task_update`、`task_claim`、`task_complete`、`task_cancel`
- 后台任务：`background_list`、`background_get`
- 定时调度：`schedule_cron`、`list_crons`、`cancel_cron`
- 团队协作：`spawn_teammate`、`team_send_message`、`team_broadcast`、`team_check_inbox`、`team_list`
- 团队协议：`team_request_shutdown`、`team_review_plan`、`team_protocol_status`
- Worktree：`worktree_create`、`worktree_bind`、`worktree_list`、`worktree_status`、`worktree_keep`、`worktree_remove`

## 运行态说明

项目会在本地生成多个运行态目录：

| 目录 | 说明 |
|---|---|
| `.tasks/` | 持久任务、任务索引、任务事件 |
| `.team/` | 团队成员、inbox、协议请求、自治事件 |
| `.runtime-tasks/` | 后台命令和定时任务事件 |
| `.memory/` | 长期记忆 |
| `.task_outputs/` | 大型工具输出落盘 |
| `.transcripts/` | 压缩前会话转录 |
| `.worktrees/` | worktree 索引和事件 |
| `logs/` | 运行日志 |

这些目录用于调试和恢复，不应提交敏感内容。

## 开发文档

`docs/` 中按阶段记录了项目能力演进：

1. Agent 循环
2. 工具调用
3. 权限控制
4. Hook 机制
5. 计划管理
6. 子 Agent
7. 技能加载
8. 上下文压缩
9. 长期记忆
10. 系统提示词
11. 错误恢复
12. 任务系统
13. 后台任务
14. 定时调度器
15. 智能体团队
16. 团队协议
17. 自治智能体
18. 工作树隔离
19. MCP Tools

## 安全注意事项

- 不要把真实 API Key 写入 README、文档或提交历史。
- `.env` 应只保存在本地。
- `write_file`、`edit_file`、`worktree_remove` 等高风险工具默认应经过审批。
- `bash` 会拦截常见危险命令，但仍应谨慎开放给模型。
- Worktree 删除会丢弃隔离目录中的改动，使用 `discard_changes=true` 前应先确认。

## 适用场景

这个项目适合用于学习和实验：

- 如何实现一个可调用工具的 Agent Loop。
- 如何把权限、Hook、记忆、压缩和错误恢复拆成独立模块。
- 如何把大目标拆成持久任务图。
- 如何让多个 Agent 通过文件 inbox 协作。
- 如何让 teammate 自动认领任务并在隔离 worktree 中执行。

项目重点是清晰、可读、可逐步扩展的 Agent Runtime 架构。
