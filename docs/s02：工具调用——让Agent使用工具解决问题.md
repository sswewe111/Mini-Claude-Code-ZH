# s02：工具调用——让Agent使用工具解决问题

## 目标

s02 在 s01 的 Agent Loop 上接入工具调用能力。模型不再只能回答文本，而是可以请求程序执行工具，把真实结果写回上下文，再继续推理。

当前实现基于 OpenAI Chat Completions 原生工具格式：

```python
client.chat.completions.create(
    model=model_id,
    messages=messages,
    tools=BASE_TOOLS,
    tool_choice="auto",
)
```

## 当前代码结构

```text
agent_loop.py
tools_configs/
├── __init__.py
└── base_configs.py
handlers/
├── __init__.py
├── base_handlers.py
└── dispatcher.py
tools/
├── bash_tools.py
└── file_tools.py
utils/
├── path_sandbox.py
├── normalize_messages.py
└── logger_handler.py
```

## 工具列表

当前基础工具有 4 个：

| 工具 | 作用 |
| --- | --- |
| `bash` | 在当前工作区执行命令 |
| `read_file` | 读取工作区内文件 |
| `write_file` | 写入工作区内文件 |
| `edit_file` | 对工作区内文件做精确文本替换 |

这些工具定义在 `tools_configs/base_configs.py` 中，格式是 OpenAI tools schema：

```python
{
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "...",
        "parameters": {...},
    },
}
```

## 工具调用链路

完整链路如下：

```text
模型返回 tool_calls
  -> agent_loop.py 保存 assistant message
  -> dispatcher.py 解析 tool_call
  -> base_handlers.py 查找工具处理函数
  -> tools/*.py 执行真实操作
  -> agent_loop.py 写回 tool message
  -> 下一轮模型调用读取工具结果
```

`agent_loop.py` 不直接写具体工具逻辑，只负责调用：

```python
result = dispatch_tool_call(tool_call)
```

这样后续新增工具时，主循环不需要改。

## dispatcher 如何解析 arguments

OpenAI SDK 返回的工具调用对象中，参数来自：

```python
tool_call.function.arguments
```

它通常是模型生成的 JSON 字符串，例如：

```json
{"path": "data/summer.txt"}
```

`handlers/dispatcher.py` 会执行：

```python
args = json.loads(raw_args or "{}")
```

如果模型返回非法 JSON，dispatcher 会返回明确错误，不让主循环崩溃。

## bash 工具

`tools/bash_tools.py` 会先判断当前系统：

- Windows：使用 PowerShell。
- Linux/macOS：使用 `bash -lc`。
- 其他系统：使用系统 shell 兜底。

返回结果包含：

```text
shell: powershell
exit_code: 0
stdout:
...
stderr:
...
```

这样测试时可以明确知道命令跑在哪种 shell 下。

## 文件工具和路径沙箱

文件工具定义在 `tools/file_tools.py`：

- `read_file(path, limit=None)`
- `write_file(path, content)`
- `edit_file(path, old_text, new_text)`

每个文件路径都会先经过：

```python
safe_path(path)
```

`utils/path_sandbox.py` 会把路径限制在当前工作区内，避免模型读写工作区外的文件。

## 消息规范化

`utils/normalize_messages.py` 会保留 OpenAI Chat Completions 接口需要的字段：

- `role`
- `content`
- `tool_calls`
- `tool_call_id`
- `name`

这一步可以剥离内部临时字段，避免把不属于 OpenAI 消息协议的内容传给模型。

## 日志

日志由 `utils/logger_handler.py` 输出。

s02 中重点观察：

- 模型是否请求工具。
- dispatcher 分发了哪个工具。
- 工具参数是什么。
- bash 使用的是 PowerShell 还是 bash。
- 文件工具是否触发路径沙箱。
- 工具结果是否写回 messages。

## 固定测试任务

当前 `agent_loop.py` 使用固定任务：

```python
请获取当前目录下的所有文件，展示给我，然后找到summer.txt文件将里面的内容总结给我
```

理想执行过程：

1. 模型调用 `bash` 查看当前目录。
2. 模型发现或继续查找 `data/summer.txt`。
3. 模型调用 `read_file` 读取内容。
4. 模型基于工具结果用中文总结。

## 验收标准

- `BASE_TOOLS` 中 4 个工具名唯一。
- `BASE_HANDLERS` 覆盖 4 个工具。
- `bash` 能根据系统选择 PowerShell 或 bash。
- `read_file`、`write_file`、`edit_file` 都经过 `safe_path()`。
- OpenAI tool call 的 `arguments` 能被解析为 dict。
- 工具结果以 `{"role": "tool", "tool_call_id": ..., "content": ...}` 写回消息。
- 模型能基于工具结果继续下一轮推理。

## 下一步

s03 会在工具执行前加入权限判断，避免危险命令或高风险文件操作直接执行。
