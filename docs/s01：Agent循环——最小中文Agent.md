# s01：Agent循环——最小中文Agent

## 目标

这一阶段实现最小 Agent Loop：程序读取模型配置，构造中文系统提示词，把用户任务交给模型，并把模型回复保存到会话历史中。

当前项目的入口是根目录下的 `agent_loop.py`。它不是一个独立 CLI 框架，而是一个教学用主文件：固定任务、固定工作区、固定工具池，便于观察 Agent Loop 如何运行。

## 当前代码结构

```text
agent_loop.py
model_client.py
state/
└── agent_state.py
prompts/
└── system_prompts.py
utils/
├── logger_handler.py
└── normalize_messages.py
```

## 核心文件

### `agent_loop.py`

`agent_loop.py` 是主文件，负责：

- 读取 `.env` 中的模型配置。
- 创建 OpenAI SDK 客户端。
- 初始化 `LoopState`。
- 构造 OpenAI Chat Completions messages。
- 调用模型。
- 把 assistant 回复写回 `state.messages`。
- 在模型不再请求工具时结束循环。

当前固定任务是：

```python
question = "请获取当前目录下的所有文件，展示给我，然后找到summer.txt文件将里面的内容总结给我"
```

固定任务的目的是稳定测试：模型应该先查看目录，再定位 `summer.txt`，再读取文件内容并总结。

### `model_client.py`

`model_client.py` 只负责创建 OpenAI SDK 客户端：

```python
from openai import OpenAI

OpenAI(api_key=api_key, base_url=base_url)
```

具体环境变量读取仍然放在 `agent_loop.py`，这样工具函数不会各自读取 `.env`。

### `state/agent_state.py`

`LoopState` 保存一次运行需要的最小状态：

```python
@dataclass
class LoopState:
    messages: list
    turn_count: int = 0
```

- `messages`：OpenAI Chat Completions 格式的消息列表。
- `turn_count`：模型调用轮次，方便日志排查。

### `prompts/system_prompts.py`

提示词使用中文。当前实际使用的是 `SYSTEM_WITH_TOOLS`，因为 s02 已经接入工具。

它明确要求模型：

- 使用工具查看文件和执行命令。
- 不编造文件内容或命令输出。
- 根据工具返回结果继续分析。
- 用中文回答用户。

## Agent Loop 流程

```text
程序启动
  -> 读取 .env
  -> 创建 OpenAI client
  -> 初始化 LoopState
  -> 构造 system + user messages
  -> 调用 client.chat.completions.create(...)
  -> 保存 assistant message
  -> 如果没有 tool_calls，返回最终回答
```

s01 关注的是循环骨架。工具调用的细节在 s02 展开。

## 日志

日志由 `utils/logger_handler.py` 提供，默认写入 `logs/`，同时输出到控制台。

s01 中重点观察：

- 程序是否启动。
- `.env` 是否正确读取。
- 模型配置是否能创建客户端。
- Agent 循环进入第几轮。
- 模型是否结束循环。

## 运行方式

确保 `.env` 包含：

```env
ANTHROPIC_BASE_URL=...
ANTHROPIC_AUTH_TOKEN=...
MODEL_ID=...
```

安装依赖：

```powershell
pip install -r requirements.txt
```

运行：

```powershell
python agent_loop.py
```

## 验收标准

- `python agent_loop.py` 能读取 `.env`。
- OpenAI SDK 客户端能被创建。
- `state.messages` 使用字典消息格式。
- 模型回复会写回 `state.messages`。
- 没有使用 `ChatOpenAI`、`langchain-openai` 或 `langchain-core`。
- 日志能记录程序启动和循环状态。

## 下一步

s02 会把工具定义、工具处理器、工具函数和工具结果回写接入这个循环，让模型可以通过 `bash`、`read_file`、`write_file`、`edit_file` 解决问题。
