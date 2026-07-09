# s05：计划管理——没有计划的 Agent，做着做着就偏了

本节在 s04 Hook 机制的基础上加入 `todo` 工具，让 Agent 在多步骤任务中维护一个当前会话内的短期计划。

`todo` 不读文件、不写文件、不执行命令。它只做一件事：让模型把当前任务拆成清晰的步骤，并在执行过程中更新每一步的状态。

## 为什么需要 todo

复杂任务很容易中途偏离。例如：

> 获取当前目录文件，找到 `秋天.txt`，总结内容，并写入 `data/summary.txt`。

如果没有计划，模型可能先查看目录，再读取文件，再写入总结，但执行几轮后容易忘记还有哪一步没完成。`todo` 的作用就是把这些步骤显式写出来：

```text
1. 获取当前目录下的所有文件并展示
2. 找到并读取秋天.txt 文件内容
3. 总结秋天.txt 的内容
4. 将总结写入 data/summary.txt 文件
```

每个步骤都有状态：

- `pending`：待处理
- `in_progress`：进行中
- `completed`：已完成

同一时间最多只能有一个 `in_progress`，这样计划不会出现多个“正在做”的步骤。

## 当前项目的实现方式

本项目使用的工具名是 `todo`，不是 `todo_write`。

相关文件：

```text
configs/
└── todo_config.yml
state/
└── agent_state.py
managers/
└── todo_manager.py
tools_configs/
└── base_configs.py
handlers/
└── base_handlers.py
hooks/
├── builtin_hooks.py
└── hook_manager.py
prompts/
└── system_prompts.py
agent_loop.py
```

## 工具定义

`todo` 工具定义直接放在 `tools_configs/base_configs.py` 的 `BASE_TOOLS` 中。

参数只有一个 `items`：

```python
{
    "items": [
        {
            "content": "获取当前目录下的所有文件并展示",
            "status": "in_progress",
            "activeForm": "正在查看目录"
        }
    ]
}
```

每个计划项包含：

- `content`：计划内容
- `status`：只能是 `pending`、`in_progress`、`completed`
- `activeForm`：可选，用来描述当前正在做什么

## 计划状态管理

`managers/todo_manager.py` 中的 `TodoManager` 负责管理计划状态。

核心方法：

- `update(items)`：重写当前计划，校验状态，并重置未更新计数
- `render()`：把当前计划渲染成可读文本
- `note_round_without_update()`：记录一轮没有更新计划
- `reminder()`：超过提醒间隔后返回 reminder

计划只保存在当前 Python 进程内存中。程序退出后，计划不会持久化到文件。

渲染示例：

```text
当前计划：4/4 已完成，全部完成
1. [x] 获取当前目录下的所有文件并展示（状态: 已完成） - 已完成文件列表展示
2. [x] 找到并读取秋天.txt文件内容（状态: 已完成） - 已完成内容读取
3. [x] 总结秋天.txt的内容（状态: 已完成） - 已完成内容总结
4. [x] 将总结写入data/summary.txt文件（状态: 已完成） - 已完成写入
```

`handlers/base_handlers.py` 中的 `handle_todo()` 会把这个渲染结果返回给模型，同时通过日志输出到控制台：

```python
def handle_todo(args: dict) -> str:
    result = TODO.update(args["items"])
    logger.info("Todo 计划状态:\n%s", result)
    return result
```

## Hook 如何参与

Todo 的提醒逻辑没有写死在 `agent_loop.py` 中，而是挂在 Hook 上。

`BeforeModelCall`：

- 调用 `TODO.reminder()`
- 如果需要提醒，就向 `context.messages` 追加一条用户消息
- reminder 内容是：

```text
<reminder>请在继续执行前调用 todo 工具刷新当前计划状态。</reminder>
```

`AfterModelCall`：

- 从 `metadata["tool_names"]` 获取本轮模型请求调用的工具名
- 如果本轮调用了 `todo`，不累计未更新轮数
- 如果本轮没有调用 `todo`，调用 `TODO.note_round_without_update()`

这样设计后，`agent_loop.py` 只负责循环、调用模型、执行工具和写回工具结果。Todo 的提醒和计数都通过 Hook 挂在循环上。

## agent_loop.py 中保留了什么

`agent_loop.py` 不直接调用 `TODO.reminder()`，也不直接调用 `TODO.note_round_without_update()`。

它只在 `AfterModelCall` 时把本轮工具名放进 Hook metadata：

```python
tool_calls = assistant_message.tool_calls or []
tool_names = [tool_call.function.name for tool_call in tool_calls]
```

Hook 拿到 `tool_names` 后自己决定是否更新 Todo 计数。

## 日志输出

为了避免日志刷屏，`todo` 的 `PreToolUse` 日志不会打印完整 `args`。

现在只显示计划项数量：

```text
[hook:PreToolUse] 工具执行前: todo, items=4
```

完整计划状态由 `handle_todo()` 单独输出：

```text
Todo 计划状态:
当前计划：4/4 已完成，全部完成
...
```

其他工具仍然保留参数日志，方便排查路径、命令和文件写入内容。

## 权限控制

`todo` 已加入 `configs/permission_config.yml` 的 `tools.allow`。

因为它不访问文件系统、不执行 shell、不修改外部状态，所以默认不需要用户审批。但它仍然会经过 `PreToolUse` 权限 Hook，保持工具调用链路一致。

## 和 s04 的关系

s04 引入 Hook 机制后，s05 的 Todo 逻辑没有继续塞进循环里，而是复用 Hook：

- `BeforeModelCall` 负责提醒注入
- `AfterModelCall` 负责计划更新计数
- `PreToolUse` 负责权限检查和日志
- `PostToolUse` 负责工具执行后的输出统计

这就是“挂在循环上，不写进循环里”的实际用法。

## 验收标准

- 模型可以看到并调用 `todo` 工具。
- `todo` 调用后控制台显示当前计划状态。
- 计划项状态只能是 `pending`、`in_progress`、`completed`。
- 同一时间最多一个计划项为 `in_progress`。
- 最多支持 12 个计划项。
- 多轮未更新计划时，下一次模型调用前会注入 reminder。
- reminder 不会插入 assistant tool_calls 和 tool result 中间。
- 简单任务可以不调用 `todo`；复杂任务应先调用 `todo` 再执行。
