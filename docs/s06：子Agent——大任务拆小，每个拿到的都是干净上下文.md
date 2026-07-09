# s06：子 Agent——大任务拆小，每个拿到的都是干净上下文

s06 在当前项目中实现的是同步 `task` 子 Agent：父 Agent 把一个复杂子任务交给子 Agent，子 Agent 用自己的消息列表完成任务，最后只把结论作为工具结果返回给父 Agent。

这个机制解决的问题是：复杂任务会产生大量中间搜索、读取、命令输出和推理过程，如果全部留在主对话里，父 Agent 的上下文会很快变脏。子 Agent 把这些中间过程隔离起来，父 Agent 只拿最终结果继续决策。

## 当前实现概览

父 Agent 可见的工具是 `task`。

`task` 定义在：

```text
tools_configs/base_configs.py
```

父 Agent 的 `task` handler 定义在：

```text
handlers/base_handlers.py
```

子 Agent 自己可见的工具描述定义在：

```text
tools_configs/subagent_configs.py
```

子 Agent 自己的工具映射定义在：

```text
handlers/subagent_handlers.py
```

真正的子 Agent 循环在：

```text
subagents/task_subagent.py
```

## 文件结构

```text
configs/
└── subagent_config.yml
tools_configs/
├── base_configs.py
└── subagent_configs.py
handlers/
├── base_handlers.py
└── subagent_handlers.py
subagents/
├── __init__.py
├── fork_context.py
└── task_subagent.py
prompts/
└── subagent_prompts.py
state/
└── agent_state.py
```

## task 工具

`task` 是父 Agent 调用子 Agent 的入口。

参数：

- `description`：必填，交给子 Agent 的自包含任务描述。
- `expected_output`：可选，说明父 Agent 期望拿到什么格式或重点。

注意：`task` 没有 `mode` 参数。Fork 是否启用不由模型决定，只由配置文件决定。

配置位置：

```text
configs/subagent_config.yml
```

```yaml
SUBAGENT_MODE: "non_fork"
```

改成下面这样即可启用 Fork 模式：

```yaml
SUBAGENT_MODE: "fork"
```

## 非 Fork 模式

非 Fork 是默认模式。

特点：

- 子 Agent 从 `description` 开始。
- 不继承父 Agent 的完整对话历史。
- 父 Agent 必须把背景、目标、已知信息、限制和期望输出写清楚。
- 子 Agent 的中间消息不会进入父 Agent 的 `messages`。

适合场景：

- 独立搜索。
- 独立分析。
- 开放性调研。
- 不需要父会话上下文的旁路任务。

代码行为：

```python
return [{"role": "user", "content": content}]
```

也就是子 Agent 初始消息只有当前子任务。

## Fork 模式

Fork 模式通过配置开启：

```yaml
SUBAGENT_MODE: "fork"
```

当前项目的 Fork 不是 Claude Code 那种 prompt cache / KV cache 复用。这里的 Fork 指：

```text
继承父 Agent 上下文快照 + 隔离子 Agent 中间过程
```

Fork 模式会使用：

```text
subagents/fork_context.py
```

构造子 Agent 的初始消息。

关键配置：

```yaml
FORK_CONTEXT_MAX_MESSAGES: 12
FORK_CONTEXT_MAX_CHARS: 12000
FORK_INCLUDE_TOOL_RESULTS: false
FORK_SUMMARIZE_PARENT_CONTEXT: true
FORK_REQUIRE_SELF_CONTAINED_DESCRIPTION: true
```

默认情况下，Fork 上下文会排除 `tool` 消息，避免把大量工具输出带入子 Agent。只有配置 `FORK_INCLUDE_TOOL_RESULTS: true` 时才会包含 tool result。

Fork 模式仍然要求 `description` 自包含。不能写“根据上文自己处理”，因为子 Agent 只拿到父上下文快照，不是父 Agent 本体。

## 子 Agent 可用工具

子 Agent 默认只使用：

- `bash`
- `read_file`
- `write_file`
- `edit_file`

这些工具定义在：

```text
tools_configs/subagent_configs.py
```

映射在：

```text
handlers/subagent_handlers.py
```

子 Agent 看不到：

- `task`
- `todo`

这样可以避免递归创建子 Agent，也避免子 Agent 覆盖父 Agent 的计划。

## 权限控制

子 Agent 的工具调用仍然经过 `PreToolUse` 和 `PostToolUse` Hook。

也就是说：

- 删除类 bash 命令会被危险关键字拦截。
- `write_file` 和 `edit_file` 仍然需要用户审批。
- 子 Agent 不会因为上下文隔离而绕过权限控制。

日志中会出现 `[subagent]` 前缀，用来区分父 Agent 和子 Agent：

```text
[subagent] task 工具启动子 Agent
[subagent] 开始第 1 轮循环
[subagent] 准备执行工具: bash
```

## 运行流程

父 Agent 调用 `task` 后：

1. `dispatcher` 分发到 `handle_task`。
2. `handle_task` 调用 `run_task_subagent(...)`。
3. 子 Agent 根据 `SUBAGENT_MODE` 决定非 Fork 或 Fork。
4. 子 Agent 使用 `SUBAGENT_SYSTEM_PROMPT` 和自己的 `messages` 调用模型。
5. 子 Agent 只能调用允许列表里的基础工具。
6. 子 Agent 工具调用仍经过 Hook 权限检查。
7. 子 Agent 完成后只返回最后的 assistant 文本。
8. 父 Agent 把这个文本作为 `task` 的 tool result 写回主上下文。

父 Agent 不会收到子 Agent 的完整中间对话。

## 边界和限制

当前 s06 实现的是同步前台子 Agent。

也就是说，父 Agent 会等待子 Agent 返回结果后再继续。

后台子 Agent、完成通知、异步任务等能力不在 s06 中实现，后续留给 Background Tasks 相关章节。

子 Agent 也不是独立权限主体。它共享当前项目文件系统，但具体读写和命令执行仍受同一套权限 Hook 约束。

## 验收标准

- 父 Agent 能通过 `task` 启动子 Agent。
- `task` 工具只暴露 `description` 和 `expected_output`。
- Fork 是否启用只由 `configs/subagent_config.yml` 的 `SUBAGENT_MODE` 决定。
- 子 Agent 默认非 Fork，不继承父 Agent 完整历史。
- Fork 模式会继承父 Agent 上下文快照。
- 子 Agent 中间工具调用不会写入父 Agent `messages`。
- 子 Agent 默认不能调用 `task` 和 `todo`。
- 子 Agent 工具调用仍经过权限 Hook。
- 子 Agent 超过 `MAX_SUBAGENT_TURNS` 会停止。
- 子 Agent 结果超过 `SUBAGENT_RESULT_MAX_CHARS` 会截断。
