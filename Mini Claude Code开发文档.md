# Mini Claude Code 渐进式重构开发文档

## 1. 文档目标

本文档用于指导 `D:\学习资料整理\Interview Record\Mini Claude Code` 的重构开发。设计依据来自：

- 学习文档：`D:\学习资料整理\Interview Record\Mini Claude Code-zh\docs\s01` 到 `s20`

重构方式采用“由简到难、由基础到完整”的路线：先实现最小 Agent Loop，再逐步加入工具、权限、Hook、计划、子 Agent、技能、压缩、记忆、任务系统、后台任务、定时调度、团队协作、Worktree 隔离、MCP，最后把所有能力归入一个清晰的主循环。

这份文档不是一次性大改方案，而是 20 个阶段的开发蓝图。每个阶段都说明：

- 本阶段要完成什么。
- 需要实现什么能力。
- 使用什么文件夹存放什么文件。
- 如何验收。

## 2. 总体目录设计

最终建议目录结构如下：

```text
Mini Claude Code/
├── agent_loop.py                  # 主文件：启动入口 + 主 Agent 循环
├── README.md
├── .env                           # API Key、模型、base url 等真实环境变量
├── configs/                       # YAML/JSON 配置
├── prompts/                       # 提示词片段
├── tools_configs/                 # 模型可见的工具定义 schema
├── handlers/                      # 工具名到处理函数的映射和调度
├── tools/                         # 模型可调用工具背后的函数
├── subagents/                     # 子 Agent 实现
├── managers/                      # 有状态、生命周期较复杂的管理器
├── mcp/                           # MCP/插件接入层
├── state/                         # Agent 状态 dataclass
├── utils/                         # 非模型工具的通用函数
├── skills/                        # Skill 包，每个 skill 包含 SKILL.md
├── docs/                          # 项目自身文档
├── tests/                         # 自动化测试
├── .memory/                       # 长期记忆运行时数据
├── .tasks/                        # 持久任务看板
├── .team/                         # 团队成员、inbox、请求状态
├── .runtime-tasks/                # 后台任务运行状态
├── .task_outputs/                 # 大型工具输出落盘
├── .transcripts/                  # 压缩前会话转录
└── .worktrees/                    # worktree 索引和事件流
```

核心分层规则：

- `agent_loop.py`：作为主文件，负责启动入口和 Agent 循环编排；当前用固定任务初始化状态，可以读取 `.env`，但不写具体工具实现。
- `prompts/`：只放提示词文本和片段，不执行工具、不读写状态。
- `tools_configs/`：只放模型可见的工具 schema。
- `handlers/`：只做工具名到函数的映射、参数适配、权限/Hook 管线调度。
- `tools/`：放模型可以通过 tool call 间接调用的函数。
- `subagents/`：放子 Agent 的独立循环和上下文隔离逻辑。
- `utils/`：放模型不能直接调用、但其他模块会复用的通用函数，例如路径沙箱、配置读取、模型客户端、消息规范化。项目不单独拆 `cli.py` 和 `env.py`，统一由 `agent_loop.py` 作为主入口。
- `managers/`：放有状态、跨工具共享、生命周期复杂的能力，例如任务、记忆、后台任务、团队、worktree。

## 3. 基础工程准备

在进入 s01 之前，先完成基础工程结构。

要完成：

- 创建新目录结构。
- 统一环境变量读取。
- 统一模型客户端创建。
- 建立最小可运行入口。

建议文件：

```text
configs/
├── model_config.yml
└── runtime_config.yml
utils/
├── logger_handler.py
└── runtime_paths.py
state/
└── agent_state.py
agent_loop.py
model_client.py
.env
```

实现要求：

- `.env` 保存 API Key、模型名称、base url 等环境变量，开发时只维护这一份环境配置文件。
- `agent_loop.py` 启动时读取 `MODEL_BASE_URL`、`MODEL_API_KEY`、`MODEL_ID`，兼容旧变量 `ANTHROPIC_BASE_URL`、`ANTHROPIC_AUTH_TOKEN`。
- 根目录 `model_client.py` 负责根据 `agent_loop.py` 传入的模型配置创建 OpenAI SDK 客户端。
- `utils/runtime_paths.py` 统一定义 `.memory/`、`.tasks/`、`.team/` 等运行时路径。

验收：

- `python agent_loop.py` 可以读取环境变量并启动最小 Agent。
- 任意模块不再自己散落 `load_dotenv()`。

## 4. s01: Agent Loop

主题：一个循环就够了。

目标：

- 实现最小中文 Agent 循环骨架。
- 使用 OpenAI SDK 调用 OpenAI-compatible 接口。
- 使用 `.env` 中的 `ANTHROPIC_BASE_URL`、`ANTHROPIC_AUTH_TOKEN`、`MODEL_ID` 创建模型客户端。
- 用字典格式维护 OpenAI Chat Completions messages。

要完成什么：

- 建立 `LoopState`。
- 建立 `agent_loop(state, client, model_id)`。
- 用 `OpenAI` client 调用 `client.chat.completions.create(...)`。
- 使用中文 system prompt。
- 将 assistant 回复追加到 messages。
- 当没有工具调用时结束。
- 当前代码中固定任务写在 `agent_loop.py`，用于稳定测试工具调用链路。

文件设计：

```text
agent_loop.py
model_client.py
state/
└── agent_state.py
utils/
├── logger_handler.py
└── normalize_messages.py
prompts/
├── __init__.py
└── system_prompts.py
```

实现内容：

- `state/agent_state.py`
  - `LoopState(messages, turn_count)`
  - `messages` 保存 OpenAI Chat Completions 字典消息。
  - `turn_count` 记录模型调用轮次，便于日志观察循环行为。
- `prompts/system_prompts.py`
  - `SYSTEM_WITH_TOOLS`：中文系统提示词。
  - 即使 s01 是基础循环，也直接使用最终 s02 工具提示词，避免重复维护两套 prompt。
- `model_client.py`
  - 从 `openai` 导入 `OpenAI`。
  - 根据 `base_url` 和 `api_key` 创建 OpenAI SDK 客户端。
- `utils/logger_handler.py`
  - 输出控制台日志和 `logs/` 文件日志，方便检查每轮循环和工具执行情况。
- `agent_loop.py`
  - 使用 `python-dotenv` 读取 `.env`。
  - 使用固定任务：`请获取当前目录下的所有文件，展示给我，然后找到summer.txt文件将里面的内容总结给我`。
  - 初始化 `LoopState`。
  - 用字典格式维护 messages，例如 `{"role": "user", "content": "..."}`
  - 调用 `client.chat.completions.create(model=model_id, messages=messages, tools=BASE_TOOLS, tool_choice="auto")`。
  - 将 assistant 回复写回 `state.messages`。
  - 返回最终 assistant 文本。

验收：

- 运行 `python agent_loop.py` 后能读取 `.env` 并创建 OpenAI 客户端。
- `agent_loop.py` 只负责编排循环，不实现具体工具逻辑。
- 不依赖 `ChatOpenAI`、`langchain-openai` 或 `langchain-core`。

## 5. s02: Tool Use

主题：多加一个工具，只加一行。

目标：

- 加入工具定义、工具处理器、工具执行结果回写。
- 使用 OpenAI Chat Completions 原生 tools/tool_calls 格式。
- 形成工具三件套：schema、handler、tool function。

要完成什么：

- 支持 `bash`、`read_file`、`write_file`、`edit_file`。
- 模型发起 tool call 后，主循环执行工具。
- 工具结果以 `tool` message 写回上下文。
- `agent_loop.py` 调用模型前使用 `normalize_messages()` 清理消息。
- 文件工具使用 `safe_path()` 限制读写范围。
- `bash` 工具根据当前系统自动选择 PowerShell 或 bash。
- dispatcher 解析 OpenAI SDK 返回的 `tool_call.function.arguments` JSON 字符串。

文件设计：

```text
agent_loop.py
model_client.py
prompts/
└── system_prompts.py
tools_configs/
├── __init__.py
└── base_configs.py
handlers/
├── __init__.py
├── dispatcher.py
└── base_handlers.py
tools/
├── __init__.py
├── bash_tools.py
└── file_tools.py
utils/
├── logger_handler.py
├── path_sandbox.py
└── normalize_messages.py
```

实现内容：

- `tools_configs/base_configs.py`
  - 定义 `BASE_TOOLS`。
  - 包含 `bash`、`read_file`、`write_file`、`edit_file` schema。
  - schema 采用 OpenAI tools 格式：`{"type": "function", "function": {...}}`。
- `tools/bash_tools.py`
  - 实现 `run_bash(command)`。
  - Windows 使用 PowerShell：`powershell -NoProfile -ExecutionPolicy Bypass -Command ...`。
  - Linux/macOS 使用 bash：`bash -lc ...`。
  - 返回 exit code、stdout、stderr。
- `tools/file_tools.py`
  - 实现 `read_file(path, limit)`。
  - 实现 `write_file(path, content)`。
  - 实现 `edit_file(path, old_text, new_text)`。
  - 所有文件路径先经过 `utils/path_sandbox.py` 的 `safe_path()`。
- `handlers/base_handlers.py`
  - 建立工具名到函数的映射。
- `handlers/dispatcher.py`
  - 解析 OpenAI SDK 返回的 `tool_call.function.name` 和 `tool_call.function.arguments`。
  - `arguments` 来自模型根据 tools schema 生成的 JSON 字符串，例如 `{"path": "data/summer.txt"}`。
  - JSON 解析失败时返回明确错误，不让主循环崩溃。
  - 查找 handler。
  - 返回标准 tool result。
- `agent_loop.py`
  - 调用模型时传入 `tools=BASE_TOOLS` 和 `tool_choice="auto"`。
  - 如果没有 `tool_calls`，返回最终回答。
  - 如果有 `tool_calls`，先把 assistant message 写回 `state.messages`。
  - 对每个 tool call 调用 dispatcher。
  - 将工具结果追加为 `{"role": "tool", "tool_call_id": ..., "content": ...}`。
  - 继续下一轮模型调用，让模型读取工具结果后生成最终回答。
  - 只调用 dispatcher，不写具体工具判断。

验收：

- 所有工具 schema 的 name 全局唯一。
- 每个本地工具都有 handler。
- 模型可以请求 `read_file`，工具结果能回写给模型。
- 模型可以请求 `bash` 查看目录或执行简单命令。
- 文件工具不能读取或写入工作区外路径。
- 日志能记录模型循环、工具分发、bash 执行、文件读写。
- 不使用 `ChatOpenAI.bind_tools()`，而是使用 OpenAI SDK 原生 `tools` 参数。

## 6. s03: Permission

主题：执行前做权限判断。

目标：

- 在工具执行前统一经过权限管线，避免模型直接执行危险操作。
- 使用 `permission_config.yml` 管理工具 allow/deny、危险 bash 命令和审批模式。
- 保留 s02 的 `path_sandbox.py` 作为工具层最后防线；权限层负责“是否允许尝试执行”，工具层继续负责“路径不能真正越界”。

要完成什么：

- 新增权限配置文件，集中描述允许工具、拒绝工具、危险命令关键字和审批模式。
- 新增配置读取模块，借鉴原项目 `utils/config_handler.py`，但当前阶段只读取权限配置。
- 新增权限检查模块，按三道闸门执行：
  - 闸门 1：拒绝列表，命中 deny 工具或危险命令关键字时直接拒绝。
  - 闸门 2：规则匹配，检查工具是否在 allow 列表内；`read_file` 只要路径在当前项目内就直接允许。
  - 闸门 3：用户审批，项目外读取、写文件、编辑文件都需要用户确认。
- 修改 `handlers/dispatcher.py`，在找到 handler 之后、真正执行 handler 之前调用权限检查。

文件设计：

```text
configs/
└── permission_config.yml
utils/
├── config_handler.py
├── permission_check.py
└── path_sandbox.py
state/
└── permission_state.py
handlers/
└── dispatcher.py
```

实现内容：

- `configs/permission_config.yml`
  - `tools.allow`：允许模型调用的工具，例如 `bash`、`read_file`、`write_file`、`edit_file`。
  - `tools.deny`：任何情况下都不允许调用的工具，优先级高于 allow。
  - `dangerous_commands`：危险命令关键字，例如 `rm -rf`、`rm`、`del`、`Remove-Item`、`Format-Volume`。
  - `approval.mode`：用户审批模式，支持 `ask`、`auto_allow`、`auto_deny`。
  - `approval.required_tools`：需要进入人工审批的工具，例如 `write_file`、`edit_file`。
- `utils/config_handler.py`
  - `load_yaml_config(path, default=None)`：用 `safe_path()` 限制配置文件只能从项目内读取。
  - `load_permission_config()`：读取 `configs/permission_config.yml`，返回 dict。
  - 缺少 `pyyaml` 时使用轻量 YAML 解析兜底，保证当前配置仍可读取。
  - `permission_config`：模块级默认配置，供权限模块复用。
- `state/permission_state.py`
  - `PermissionResult`：包含 `allowed`、`reason`、`needs_approval`。
- `utils/permission_check.py`
  - `check_permission(tool_name, args, config=None)`：执行三道闸门并返回权限结果。
  - `request_user_approval(tool_name, args, reason)`：用户审批入口。
  - `_contains_dangerous_keyword()`：对单个命令词按边界匹配，例如 `del file /f /q` 和 `cmd /c del file` 都能命中 `del`。
  - `read_file`：当前项目内直接允许；项目外路径进入审批。
  - `write_file`、`edit_file`：不按路径范围细分，统一进入审批。
- `handlers/dispatcher.py`
  - 解析 tool_call 参数后，先检查工具是否存在。
  - 调用 `check_permission(name, args)`。
  - 权限拒绝时返回 `Permission denied: ...` 给模型，不执行工具函数。
  - 权限通过后保持 s02 的 handler 分发逻辑。

推荐配置示例：

```yaml
tools:
  allow:
    - bash
    - read_file
    - write_file
    - edit_file
  deny: []

dangerous_commands:
  - "rm -rf"
  - "rm"
  - "del"
  - "erase"
  - "rd"
  - "rmdir"
  - "Remove-Item"
  - "Format-Volume"
  - "shutdown"
  - "reboot"

approval:
  mode: "ask"
  required_tools:
    - write_file
    - edit_file
```

验收：

- 危险 bash 命令被拦截，例如 `del summary.txt /f /q`、`cmd /c del /f /q summary.txt`。
- deny 工具即使出现在 allow 中也会被拒绝。
- `read_file` 读取当前项目内路径时直接允许。
- `read_file` 读取项目外路径时进入用户审批；当前文件工具仍有 `safe_path()` 兜底，审批通过也不会绕过工具层沙箱。
- `write_file` 和 `edit_file` 不管目标路径在哪里，都会先进入用户审批。
- 用户拒绝或终端无法输入时，不会调用真实工具函数。
- 权限判断不散落在每个工具函数里。

## 7. s04: Hooks

主题：挂在循环上，不写进循环里。

目标：

- 在 Agent 生命周期的固定时机暴露扩展点，让日志、输入改写、工具前后处理可以挂在 hook 上。
- 保持 `agent_loop.py` 和 `handlers/dispatcher.py` 的主流程稳定，不因为每新增一个检查就继续膨胀。
- 保留 s03 权限系统作为硬安全门；权限检查已经包装成 final `PreToolUse` hook。普通 hook 可以记录日志、阻止工具，但不能修改工具参数或绕过权限 deny。

要完成什么：

- 实现一个轻量 `HookManager`，负责读取配置、匹配事件、执行 hook、收集结构化结果。
- 支持六个事件：
  - `SessionStart`：程序启动后触发，用于初始化检查和启动日志。
  - `BeforeModelCall`：调用模型前触发，用于观察或追加上下文。
  - `AfterModelCall`：模型返回后触发，用于记录 token、finish reason、是否请求工具。
  - `PreToolUse`：工具执行前触发，用于日志、权限检查、非权限类拦截。
  - `PostToolUse`：工具执行后触发，用于输出审查、追加说明、记录工具结果。
  - `Stop`：Agent 即将返回最终答案前触发，用于收尾统计。
- Hook 支持两种来源：
  - Python 内置 hook：项目内函数，适合日志、统计、测试。
  - 配置命令 hook：从 `configs/hooks_config.yml` 读取命令，适合模拟 Claude Code 的外部 hook；当前默认关闭。
- Hook 返回结构化 `HookResult`，而不是随意抛异常中断循环。
- `PreToolUse` 的执行顺序必须清晰：先运行普通 hook 记录或阻止执行，再运行 final 权限 hook；即使普通 hook 表示 allow，也必须继续经过权限检查。

文件设计：

```text
configs/
└── hooks_config.yml
state/
└── hook_state.py
utils/
└── config_handler.py
hooks/
├── builtin_hooks.py
└── hook_manager.py
handlers/
└── dispatcher.py
agent_loop.py
```

实现内容：

- `configs/hooks_config.yml`
  - `enabled`：是否启用配置命令 hook；当前默认 `false`。
  - `timeout_seconds`：单个 hook 命令最大运行时间，默认 30 秒。
  - `trust.require_marker`：是否要求工作区存在信任标记才运行外部命令 hook。
  - `trust.marker_path`：信任标记路径，例如 `.mini_claude_code_trusted`。
  - `events`：按事件配置 hook 列表。
  - 每个 hook 包含 `name`、`matcher`、`command`、`enabled`。
- `utils/config_handler.py`
  - 新增 `DEFAULT_HOOKS_CONFIG`。
  - 新增 `load_hooks_config(config_file="configs/hooks_config.yml")`。
  - 新增模块级 `hooks_config`。
- `state/hook_state.py`
  - `HookContext`：保存事件上下文，例如 `event`、`tool_name`、`tool_input`、`tool_output`、`messages`。
  - `HookResult`：统一保存 `blocked`、`block_reason`、`updated_output`、`errors`。
- `hooks/hook_manager.py`
  - `register(event, callback, matcher="*", name=None)`：注册 Python hook。
  - `register(..., final=True)`：注册 final hook；当前用于让权限检查最后运行。
  - `run_hooks(event, context)`：执行某个事件下匹配的所有 hook。
  - 执行顺序：普通 Python hook -> 配置命令 hook -> final Python hook。
  - 根据 `matcher` 过滤工具名，`*` 表示匹配全部工具。
  - 执行配置命令 hook 时，把上下文写入环境变量：
    - `HOOK_EVENT`
    - `HOOK_TOOL_NAME`
    - `HOOK_TOOL_INPUT`
    - `HOOK_TOOL_OUTPUT`
  - 命令退出码约定：
    - `0`：通过；如果 stdout 是 JSON，可读取 `updatedOutput`；`message` / `additionalContext` 只记录日志，不注入对话。
    - `1`：阻止执行；stderr 作为 `block_reason`。
    - `2`：不中断，但把 stderr 作为附加上下文。
  - Hook 超时或异常时记录日志，写入 `errors`，默认不杀掉主循环。
- `hooks/builtin_hooks.py`
  - `log_session_start(context)`：记录程序启动。
  - `log_before_model_call(context)`：记录消息数量和模型名。
  - `log_after_model_call(context)`：记录模型是否请求工具。
  - `log_pre_tool_use(context)`：记录工具名和参数摘要。
  - `permission_check_hook(context)`：把 s03 的 `check_permission()` 包装成 final `PreToolUse` hook。
  - `log_post_tool_use(context)`：记录工具输出长度。
- `handlers/dispatcher.py`
  - 解析 tool_call 后构造 `HookContext(event="PreToolUse", tool_name=name, tool_input=args)`。
  - 运行 `PreToolUse` hook，其中 final 权限 hook 会最后检查工具名和最终参数。
  - 如果 hook 返回 `blocked=True`，直接返回阻止原因，不执行工具函数。
  - 工具执行完成后运行 `PostToolUse` hook，可追加 hook 消息或改写输出。
  - 仍然只负责分发，不把具体日志、审查、输出处理写死在工具函数里。
- `agent_loop.py`
  - `main()` 启动后触发 `SessionStart`。
  - 模型调用前触发 `BeforeModelCall`。
  - 模型调用后触发 `AfterModelCall`。
  - 没有工具调用、即将返回最终答案前触发 `Stop`。
  - 当前生命周期 hook 主要用于日志观察；hook 返回文本只记录日志，不注入对话。
  - `agent_loop()` 可以接收 `hook_manager` 参数，便于测试时替换为禁用 hook 的实例。

当前默认配置：

```yaml
enabled: false
timeout_seconds: 30

trust:
  require_marker: false
  marker_path: ".mini_claude_code_trusted"

events: {}
```

外部命令 hook 示例：

```yaml
enabled: true
timeout_seconds: 30

trust:
  require_marker: false
  marker_path: ".mini_claude_code_trusted"

events:
  SessionStart:
    - name: "session_log"
      matcher: "*"
      enabled: true
      command: "python hooks/session_start_hook.py"
  PreToolUse:
    - name: "all_tool_log"
      matcher: "*"
      enabled: true
      command: "python hooks/log_tool_hook.py"
  PostToolUse:
    - name: "large_output_note"
      matcher: "*"
      enabled: true
      command: "python hooks/check_output_hook.py"
```

关键执行顺序：

```text
agent_loop.main
  -> SessionStart hooks

agent_loop 每一轮
  -> BeforeModelCall hooks
  -> OpenAI chat.completions.create(...)
  -> AfterModelCall hooks
  -> 如果没有 tool_calls:
       -> Stop hooks
       -> 返回最终答案

dispatcher 每个工具调用
  -> 解析工具名和参数
  -> 普通 PreToolUse hooks
  -> final PreToolUse permission_check_hook
  -> 执行 handler
  -> PostToolUse hooks
  -> 返回工具结果
```

和 s03 权限系统的关系：

- s03 权限检查仍是硬安全门。
- Hook 可以提前阻止工具执行。
- PreToolUse Hook 不支持改写工具参数；权限检查始终检查模型原始工具参数。
- Hook 不能通过返回 allow 来覆盖 `permission_config.yml` 的 deny 规则，也不能绕过危险 bash 命令拦截。
- 权限拒绝时不运行真实工具函数，也不运行 `PostToolUse`，避免把被拒绝操作当成已执行操作记录。

验收：

- 启动程序时可以触发 `SessionStart` 日志 hook。
- 每次模型调用前后可以看到 `BeforeModelCall`、`AfterModelCall` 日志。
- 每次工具调用前后可以看到 `PreToolUse`、`PostToolUse` 日志。
- `PreToolUse` hook 返回 `blocked=True` 时，真实工具函数不会执行。
- `PreToolUse` hook 不会修改工具参数，只负责记录、拦截和权限控制。
- 危险 bash 命令即使被 hook 标记为 allow，也仍会被权限系统拒绝。
- Hook 命令超时、异常、JSON 解析失败时不会直接杀掉主循环，错误会进入 `HookResult.errors` 并写入日志。
- 不启用配置命令 hook 时，Python 内置 hook 仍可运行；完全禁用 hook 时，s03 工具调用链路仍保持可用。

## 8. s05: TodoWrite

主题：没有计划的 Agent，做着做着就偏了。

目标：

- 加入当前会话内的轻量计划工具 `todo`，让 Agent 在复杂任务中显式维护短期计划。
- 计划只保存在当前进程内存中，不读写文件，不增加执行能力，只增加规划能力。
- 在多轮未更新计划时通过 Hook 自动提醒模型刷新计划，避免长任务中途偏离目标。

要完成什么：

- 实现 `todo` 工具 schema，并加入 `BASE_TOOLS`。
- 实现 `todo` handler，并加入 `BASE_HANDLERS`。
- 实现 `TodoManager` 管理当前会话计划。
- 新增 `PlanItem` / `PlanningState` 状态结构。
- 新增 `todo_config.yml` 配置提醒间隔。
- 在 `BeforeModelCall` Hook 中注入 Todo reminder。
- 在 `AfterModelCall` Hook 中统计本轮是否调用 `todo`。
- 在系统提示词中加入中文计划规则，提醒模型复杂任务先写计划、执行中及时更新状态。

文件设计：

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

实现内容：

- `configs/todo_config.yml`
  - `PLAN_REMINDER_INTERVAL`：连续多少轮没有更新计划后提醒模型，默认 `3`。
- `utils/config_handler.py`
  - 新增 `DEFAULT_TODO_CONFIG`。
  - 新增 `load_todo_config(config_file="configs/todo_config.yml")`。
  - 新增模块级 `todo_config`。
- `state/agent_state.py`
  - 保留 `LoopState(messages, turn_count)`。
  - 新增 `PlanItem(content, status="pending", active_form="")`。
  - 新增 `PlanningState(items, rounds_since_update=0)`。
- `managers/todo_manager.py`
  - `TodoManager.update(items)`：
    - 校验最多 12 个计划项。
    - 校验 `content` 不能为空。
    - 校验 `status` 只能是 `pending`、`in_progress`、`completed`。
    - 校验最多一个 `in_progress`。
    - 支持可选 `activeForm`，用于描述当前正在做什么。
    - 更新后把 `rounds_since_update` 重置为 0。
    - 返回渲染后的计划文本。
  - `TodoManager.note_round_without_update()`：每轮未调用 `todo` 时计数 +1。
  - `TodoManager.reminder()`：超过提醒间隔时返回 `<reminder>...</reminder>`，否则返回 `None`。
  - `TodoManager.render()`：把当前计划渲染成工具结果和终端日志可读文本。
  - 渲染时显示进度摘要、每项状态中文标签，以及全部完成提示。
  - 暴露模块级单例 `TODO = TodoManager()`，方便 handler 和 Hook 共享当前计划。
- `tools_configs/base_configs.py`
  - 工具名使用 `todo`。
  - 参数名使用 `items`。
  - 每个 item 包含：
    - `content`：计划项内容。
    - `status`：`pending` / `in_progress` / `completed`。
    - `activeForm`：可选，进行时描述。
  - `required`: `["content", "status"]`。
- `handlers/base_handlers.py`
  - 直接定义 `handle_todo(args)`，不单独拆 `todo_handlers.py`。
  - `handle_todo(args)` 调用 `TODO.update(args["items"])`。
  - 使用 `logger.info("Todo 计划状态:\n%s", result)` 把计划状态输出到控制台。
  - 返回当前计划渲染文本给模型。
- `hooks/builtin_hooks.py`
  - `todo_reminder_hook(context)`：
    - 挂在 `BeforeModelCall`。
    - 调用 `TODO.reminder()`。
    - 有 reminder 时追加到 `context.messages`。
  - `todo_round_tracker_hook(context)`：
    - 挂在 `AfterModelCall`。
    - 从 `context.metadata["tool_names"]` 判断本轮是否调用 `todo`。
    - 本轮没有调用 `todo` 时调用 `TODO.note_round_without_update()`。
    - 本轮调用 `todo` 时不累计；`TODO.update()` 已经重置计数。
  - `log_pre_tool_use(context)`：
    - `todo` 只记录 `items` 数量，不打印完整 args，避免日志重复刷屏。
- `hooks/hook_manager.py`
  - 注册 `BeforeModelCall -> todo_reminder_hook`。
  - 注册 `AfterModelCall -> todo_round_tracker_hook`。
- `prompts/system_prompts.py`
  - 在 `SYSTEM_WITH_TOOLS` 中追加中文计划规则：
    - 复杂任务先调用 `todo` 列出步骤。
    - 开始某一步时把它设为 `in_progress`。
    - 完成后设为 `completed`。
    - 计划变化时重写完整 `items` 列表。
    - 简单单步问题不强制使用 `todo`。
- `agent_loop.py`
  - 不直接调用 `TODO.reminder()`。
  - 不直接调用 `TODO.note_round_without_update()`。
  - `AfterModelCall` 时把本轮模型返回的 `tool_names` 放入 `HookContext.metadata`。
  - reminder 必须在下一次模型调用前追加，不能插在 assistant tool_calls 和 tool result 中间，以免破坏 OpenAI 消息顺序。
- `configs/permission_config.yml`
  - 把 `todo` 加入 `tools.allow`。
  - `todo` 不读写文件、不执行命令，默认不需要用户审批。

推荐工具定义：

```python
BASE_TOOLS = [
    # bash / read_file / write_file / edit_file ...
    {
        "type": "function",
        "function": {
            "name": "todo",
            "description": "重写当前会话的短期任务计划，用于多步骤任务规划和进度跟踪。",
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "content": {"type": "string"},
                                "status": {
                                    "type": "string",
                                    "enum": ["pending", "in_progress", "completed"],
                                },
                                "activeForm": {
                                    "type": "string",
                                    "description": "可选，描述 in_progress 项正在进行的动作。",
                                },
                            },
                            "required": ["content", "status"],
                        },
                    },
                },
                "required": ["items"],
            },
        },
    }
]
```

Hook 中的提醒和统计策略：

```text
BeforeModelCall:
  reminder = TODO.reminder()
  if reminder:
      context.messages.append({"role": "user", "content": reminder})

AfterModelCall:
  if "todo" in metadata["tool_names"]:
      不累计未更新轮数
  else:
      TODO.note_round_without_update()
```

和 s04 Hook 的关系：

- `todo` 是模型可见工具，不是 hook。
- `todo` 调用仍然经过 `PreToolUse` 权限 hook。
- `todo` 不写文件、不执行命令，默认不需要用户审批。
- reminder 注入和未更新轮数统计都挂在 Hook 上，不写进 Agent Loop。
- `agent_loop.py` 只负责提供 `tool_names` 这类最小运行时信息。

验收：

- `BASE_TOOLS` 中包含 `todo` 工具 schema，模型能看到并调用。
- `BASE_HANDLERS` 中包含 `"todo"` handler。
- 模型调用 `todo` 后，返回当前计划文本。
- 控制台日志显示当前 Todo 计划状态。
- `todo` 的 PreToolUse 日志只显示计划项数量，不打印完整 args。
- 计划项状态只能是 `pending`、`in_progress`、`completed`。
- 同一时刻最多一个计划项为 `in_progress`。
- 超过 12 个计划项会返回错误。
- 连续 `PLAN_REMINDER_INTERVAL` 轮没有更新计划时，下一次模型调用前会注入 reminder。
- reminder 不会插入 assistant tool_calls 和 tool result 中间。
- 简单任务可以不调用 `todo`；多步骤任务应优先调用 `todo`。

## 9. s06: Subagent

主题：大任务拆小，每个拿到的都是干净上下文。

目标：

- 支持父 Agent 通过 `task` 工具启动一次性子 Agent。
- 子 Agent 使用独立 `messages`，不继承父 Agent 的完整对话历史。
- 默认使用非 Fork 模式：子 Agent 从任务描述开始，父 Agent 必须提供自包含 prompt。
- 支持通过 `configs/subagent_config.yml` 开启 Fork 模式：子 Agent 可以继承父会话的上下文快照，但中间工具噪声不写回父 Agent。
- 子 Agent 与父 Agent 共享当前项目文件系统，文件读写仍走同一套工具和权限 Hook。
- 子 Agent 完成后只把最终结论作为 `task` 工具结果返回给父 Agent，不把中间对话塞回父 Agent 上下文。

要完成什么：

- 在 `BASE_TOOLS` 中新增 `task` 工具 schema。
- 在 `BASE_HANDLERS` 中新增 `handle_task(args)`。
- 在 `subagents/` 中实现独立的子 Agent 循环。
- 新增子 Agent 专用中文系统提示词。
- 新增子 Agent 配置，例如运行模式、最大循环轮数、返回结果最大长度。
- 子 Agent 可使用基础工具，但不能继续调用 `task`，也不使用 `todo`，避免递归和污染父 Agent 计划。
- 子 Agent 的工具调用仍然经过 `PreToolUse` / `PostToolUse` Hook，权限控制不因上下文隔离而跳过。
- 为 Fork 模式补充父上下文传递设计，让 `task` handler 能拿到父 Agent 当前 `messages` 的安全快照。

文件设计：

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
└── task_subagent.py
prompts/
└── subagent_prompts.py
state/
└── agent_state.py
utils/
├── config_handler.py
└── normalize_messages.py
hooks/
├── builtin_hooks.py
└── hook_manager.py
```

实现内容：

- `configs/subagent_config.yml`
  - `SUBAGENT_MODE`：子 Agent 运行模式，默认 `"non_fork"`，可选 `"fork"`。
  - `MAX_SUBAGENT_TURNS`：子 Agent 最大循环轮数，建议默认 `20`。
  - `SUBAGENT_RESULT_MAX_CHARS`：返回给父 Agent 的最大字符数，建议默认 `6000`。
  - `ALLOWED_SUBAGENT_TOOLS`：子 Agent 可见工具列表，默认 `["bash", "read_file", "write_file", "edit_file"]`。
  - `FORK_CONTEXT_MAX_MESSAGES`：Fork 模式最多继承父会话最近多少条消息，建议默认 `12`。
  - `FORK_CONTEXT_MAX_CHARS`：Fork 模式继承父上下文的最大字符数，建议默认 `12000`。
  - `FORK_INCLUDE_TOOL_RESULTS`：是否允许继承父会话中的 tool result，默认 `false`，避免把大量工具噪声带入子 Agent。
  - `FORK_SUMMARIZE_PARENT_CONTEXT`：是否把父上下文压缩成一条背景说明，默认 `true`。
  - `FORK_REQUIRE_SELF_CONTAINED_DESCRIPTION`：Fork 模式下仍要求 `description` 自包含，默认 `true`。
- `utils/config_handler.py`
  - 新增 `DEFAULT_SUBAGENT_CONFIG`。
  - 新增 `load_subagent_config(config_file="configs/subagent_config.yml")`。
  - 新增模块级 `subagent_config`。
- `tools_configs/base_configs.py`
  - 作为工具 schema 的统一出口。
  - 定义 `SUBAGENT_TOOLS`。
  - `SUBAGENT_TOOLS` 第一版只包含父 Agent 可见的 `task` 工具。
  - 把 `SUBAGENT_TOOLS` 合并进 `BASE_TOOLS`，让父 Agent 能看到 `task`。
  - `task` 参数：
    - `description`：必填，描述要交给子 Agent 完成的子任务。
    - `expected_output`：可选，描述父 Agent 希望拿到的结果格式。
  - 不向模型暴露 `mode` 参数，Fork 是否启用只由 `configs/subagent_config.yml` 的 `SUBAGENT_MODE` 决定。
  - 工具描述要明确：适合阅读、分析、排查、生成摘要等复杂子任务；返回的是子 Agent 的最终结论。
- `tools_configs/subagent_configs.py`
  - 专门存放子 Agent 自己可见的工具描述。
  - 定义 `SUBAGENT_AVAILABLE_TOOLS`。
  - 默认包含 `bash`、`read_file`、`write_file`、`edit_file`。
  - 不包含 `task`，避免子 Agent 递归创建子 Agent。
  - 不包含 `todo`，避免子 Agent 覆盖父 Agent 的计划。
- `handlers/base_handlers.py`
  - 作为工具 handler 的统一出口。
  - 定义 `handle_task(args)`。
  - `handle_task(args, runtime_context=None)` 调用 `run_task_subagent(...)`。
  - `runtime_context` 用于接收父 Agent 当前上下文，Fork 模式需要它；非 Fork 模式可以忽略。
  - 记录日志：
    - 子 Agent 启动。
    - 子 Agent 完成。
    - 返回结果长度。
  - 返回子 Agent 最终结果，作为父 Agent 的 tool result。
  - 把 `"task": handle_task` 加入 `BASE_HANDLERS`，让 dispatcher 能分发父 Agent 的 `task` 工具。
- `handlers/subagent_handlers.py`
  - 专门存放子 Agent 自己可用的工具映射。
  - 定义 `SUBAGENT_HANDLERS`。
  - 默认包含 `bash`、`read_file`、`write_file`、`edit_file` 的 handler。
  - 不包含 `task` 和 `todo`。
- `subagents/task_subagent.py`
  - `run_task_subagent(description: str, expected_output: str = "", runtime_context=None) -> str`。
  - `_resolve_mode(config)` 只读取 `configs/subagent_config.yml` 中的 `SUBAGENT_MODE`，模型不能通过工具参数切换 Fork 模式。
  - 非 Fork 模式：
    - 子 Agent 创建全新的 `LoopState(messages=[{"role": "user", "content": description}])`。
    - 不继承父 Agent 历史。
    - 适合独立搜索、独立分析、开放性调研。
  - Fork 模式：
    - 子 Agent 从 `runtime_context.parent_messages` 构造父上下文快照。
    - 快照只作为子 Agent 初始背景，不会把子 Agent 中间工具调用写回父 Agent。
    - 适合当前任务强相关、但中间工具输出不值得留在父上下文中的调研或实现。
    - 因为当前项目使用 OpenAI Chat Completions，不直接复用 Claude Code 的 prompt cache；本项目的 Fork 重点是上下文继承和噪声隔离，不承诺 KV cache 复用。
  - 子 Agent 使用 `SUBAGENT_SYSTEM_PROMPT`，不使用父 Agent 的 `SYSTEM_WITH_TOOLS`。
  - 子 Agent 自己调用 OpenAI Chat Completions。
  - 子 Agent 工具列表来自 `ALLOWED_SUBAGENT_TOOLS` 过滤后的 `SUBAGENT_AVAILABLE_TOOLS`，默认只有 `bash/read_file/write_file/edit_file`。
  - 子 Agent 工具分发使用 `SUBAGENT_HANDLERS`，不使用父 Agent 的 `BASE_HANDLERS`。
  - 调用前要校验工具名是否在子 Agent 允许列表内。
  - 子 Agent 工具调用仍传入同一个 `hook_manager` 或默认 HookManager，因此权限检查、日志、大输出提醒等继续生效。
  - 子 Agent 到达 `finish_reason=stop` 或超过最大轮数时结束。
  - 超过最大轮数时返回明确错误或截断说明，不能无限循环。
  - 最终只返回最后一次 assistant 文本，不返回子 Agent 的完整 `messages`。
- `subagents/fork_context.py`
  - 用于隔离 Fork 上下文构造逻辑。
  - `build_fork_messages(parent_messages, description, expected_output, config)`：
    - 从父 `messages` 中提取最近 N 条或压缩摘要。
    - 默认排除 tool result；`FORK_INCLUDE_TOOL_RESULTS: true` 时才包含。
    - 必须调用 `normalize_messages()` 保证 assistant tool_calls 与 tool result 顺序合法。
    - 最终追加本次 `description`，明确这是子 Agent 的任务边界。
  - `summarize_parent_context(parent_messages, max_chars)`：
    - 第一版可以先做规则摘要，不调用模型。
    - 保留用户目标、最近文本上下文、关键文件路径、已知结论和明确限制。
- `prompts/subagent_prompts.py`
  - 定义 `SUBAGENT_SYSTEM_PROMPT`。
  - 中文规则：
    - 你是父 Agent 启动的子 Agent，只完成当前子任务。
    - 可以读取、分析、必要时修改当前项目文件。
    - 不要创建新的子 Agent。
    - 不要维护父 Agent 的 todo 计划。
    - 输出要简洁，包含结论、关键证据、已做改动和剩余风险。
  - 新增 `FORK_SUBAGENT_BOILERPLATE`：
    - 明确“你是 fork worker，不是主 Agent”。
    - 不要再创建子 Agent。
    - 不要和用户对话。
    - 不要预测父 Agent 后续动作。
    - 只在最后输出一次结构化结果。
    - 输出结构建议：`Scope / Result / Key files / Files changed / Issues`。
- `state/agent_state.py`
  - 可复用现有 `LoopState(messages, turn_count)`。
  - 如果需要更清晰，也可以新增 `SubagentState(task_id, messages, turn_count)`，但第一版不强制。
  - 新增 `ToolRuntimeContext` 或 `SubagentRuntimeContext`：
    - `parent_messages`
    - `model_id`
    - `client`
    - `hook_manager`
    - `workdir`
    - 供 `task` handler 在 Fork 模式下获取父上下文。
- `agent_loop.py`
  - 主循环不需要理解子 Agent 细节。
  - 父 Agent 只会看到 `task` 工具返回的最终结果。
  - 主循环继续负责把 `task` 的 tool result 写回 `state.messages`。
  - 调用 `dispatch_tool_call()` 时传入最小运行时上下文，例如 `ToolRuntimeContext(parent_messages=state.messages, client=client, model_id=model_id, hook_manager=hook_manager, workdir=WORKDIR)`。
  - 非 `task` 工具可以忽略该上下文；`task` 工具在 Fork 模式下使用它。
- `handlers/dispatcher.py`
  - `dispatch_tool_call(tool_call, hook_manager=None, runtime_context=None)`。
  - 调用 handler 时兼容两种签名：
    - 普通工具：`handler(args)`。
    - 需要运行时上下文的工具：`handler(args, runtime_context=runtime_context)`。
  - 第一版也可以只对 `task` 特判传入 `runtime_context`，避免影响已有工具。
- `configs/permission_config.yml`
  - 把 `task` 加入 `tools.allow`。
  - `task` 本身不直接读写文件，但它会启动子 Agent；子 Agent 内部具体工具调用仍按原权限规则审批。

运行模式设计：

```yaml
SUBAGENT_MODE: "non_fork"
MAX_SUBAGENT_TURNS: 20
SUBAGENT_RESULT_MAX_CHARS: 6000
ALLOWED_SUBAGENT_TOOLS:
  - bash
  - read_file
  - write_file
  - edit_file
FORK_CONTEXT_MAX_MESSAGES: 12
FORK_CONTEXT_MAX_CHARS: 12000
FORK_INCLUDE_TOOL_RESULTS: false
FORK_SUMMARIZE_PARENT_CONTEXT: true
FORK_REQUIRE_SELF_CONTAINED_DESCRIPTION: true
```

非 Fork 模式：

- 默认模式。
- 子 Agent 从 `description` 开始，拿到的是干净上下文。
- 父 Agent 必须像给新同事交代任务一样写清楚背景、目标、已知信息、限制和期望输出。
- 适合开放性搜索、独立调研、旁路分析。

Fork 模式：

- 通过 `SUBAGENT_MODE: "fork"` 开启。
- 模型不能通过 `task` 工具参数自行切换 Fork 模式。
- 子 Agent 继承父 Agent 的上下文快照，但子 Agent 的工具调用中间过程不写回父 Agent。
- 适合当前任务背景很重要，但中间搜索、读取、测试输出不值得留在主上下文的场景。
- Fork 模式仍要求 `description` 自包含，不能写“根据上文自己看着办”。
- Fork 模式不能让子 Agent 调用 `task`，避免递归 fork。
- Fork 模式不能主动读取或暴露子 Agent 中间 transcript；父 Agent 只处理最终结果。
- 如果后续实现后台 fork，本节只设计前台同步 fork；后台通知留给 s13 Background Tasks。

验收：

- 父 Agent 能调用 `task` 委托阅读、分析、排查类子任务。
- `tools_configs/base_configs.py` 中定义父 Agent 可见的 `SUBAGENT_TOOLS`，并汇总导出包含 `task` 的 `BASE_TOOLS`。
- `tools_configs/subagent_configs.py` 中定义子 Agent 可见的 `SUBAGENT_AVAILABLE_TOOLS`。
- `handlers/base_handlers.py` 中定义 `handle_task`，并导出包含 `"task"` 的 `BASE_HANDLERS`。
- `handlers/subagent_handlers.py` 中定义子 Agent 可用的 `SUBAGENT_HANDLERS`。
- 子 Agent 使用全新的 `messages`，不会继承父 Agent 的完整历史。
- 子 Agent 的中间工具调用不会写入父 Agent `messages`。
- 父 Agent 只收到子 Agent 的最终总结。
- 子 Agent 默认看不到 `task` 工具，不能无限递归创建子 Agent。
- 子 Agent 默认看不到 `todo` 工具，不会覆盖父 Agent 的当前计划。
- 子 Agent 的 `read_file/write_file/edit_file/bash` 仍然经过权限 Hook。
- 子 Agent 超过 `MAX_SUBAGENT_TURNS` 后会停止，并返回可理解的失败说明。
- `task` 工具结果过长时按 `SUBAGENT_RESULT_MAX_CHARS` 截断，并提示已截断。
- 复杂任务中，父 Agent 可以先用 `todo` 列计划，再用 `task` 委托其中一个子任务，最后继续更新父 Agent 计划。
- 默认配置下运行非 Fork 模式，子 Agent 不继承父 Agent 完整历史。
- 配置 `SUBAGENT_MODE: "fork"` 后，子 Agent 能获得父上下文快照。
- Fork 模式下，子 Agent 中间工具调用不会写入父 Agent `messages`。
- Fork 模式下，父 Agent 不会读取子 Agent 中间 transcript，只接收最终结果。
- Fork 上下文构造后必须通过 `normalize_messages()`，避免 OpenAI tool_call 消息顺序错误。

## 10. s07: Skill Loading

主题：用到的时候才加载。

目标：

- 支持 `skills/` 技能目录。
- 启动时只把技能摘要注入 system prompt。
- 完整 `SKILL.md` 只有在模型调用 `load_skill` 时才进入上下文。
- 避免把 docx、pdf、pptx、xlsx、web-access 等大技能一次性塞进 prompt。

要完成什么：

- 扫描当前项目下的 `skills/` 子目录。
- 每个技能目录以 `SKILL.md` 作为入口文件，例如：
  - `skills/docx/SKILL.md`
  - `skills/pdf/SKILL.md`
  - `skills/pptx/SKILL.md`
  - `skills/xlsx/SKILL.md`
  - `skills/frontend-design/SKILL.md`
  - `skills/web-access/SKILL.md`
- 解析 `SKILL.md` 顶部 YAML frontmatter 中的 `name`、`description`、`license`、`origin` 等字段。
- 建立技能注册表，只保存轻量元数据，不提前读取并注入完整正文。
- 在 system prompt 中加入“可用技能目录”，只展示技能名和用途摘要。
- 新增 `load_skill` 工具，让模型在确实需要某个技能时再加载完整 `SKILL.md`。
- 加载后的技能内容作为工具执行结果进入 messages，而不是写死在 `system_prompts.py` 中。
- 技能中的 `scripts/`、`reference.md`、`README.md` 等附加资源不自动加载，由 `SKILL.md` 指引模型后续通过已有工具按需读取。

文件设计：

```text
configs/
└── skill_config.yml
skills/
└── <skill_name>/
    ├── SKILL.md
    ├── reference.md / README.md
    └── scripts/
tools_configs/
├── base_configs.py
└── subagent_configs.py
handlers/
├── base_handlers.py
└── subagent_handlers.py
managers/
├── skill_manager.py
└── system_prompt_builder.py
state/
├── agent_state.py
└── skill_state.py
utils/
└── config_handler.py
```

实现内容：

- `configs/skill_config.yml`
  - `SKILLS_ROOT: "skills"`：技能根目录。
  - `SKILL_ENTRY_FILE: "SKILL.md"`：技能入口文件名。
  - `INJECT_SKILL_CATALOG: true`：是否把技能目录注入 system prompt。
  - `MAX_SKILL_DESCRIPTION_CHARS`：限制目录摘要长度，避免单个技能描述过长。
  - `MAX_SKILL_CONTENT_CHARS`：限制 `load_skill` 返回内容长度，避免一次工具结果过大。
  - `ALLOW_SUBAGENT_LOAD_SKILL: true`：默认允许子 Agent 加载技能，但仍然只加载技能入口说明，不自动读取附加资源。
- `managers/skill_manager.py`
  - `SkillRegistry`：技能注册表，负责扫描、缓存、查询和加载。
  - `scan_skills()`：启动时扫描 `skills/`，解析 frontmatter 和摘要。
  - 扫描阶段可以读取 `SKILL.md` 来解析元数据，但注册表只保存轻量 `SkillManifest`，不把完整正文注入 prompt。
  - `list_catalog()`：生成适合注入 prompt 的技能目录文本。
  - `load_skill(name)`：按名称读取完整 `SKILL.md`。
  - 路径必须限制在 `skills/` 根目录下，避免通过技能名访问项目外文件。
- `state/skill_state.py`
  - `SkillManifest`：技能轻量元数据，包含 `name`、`description`、`path`、`entry_file`。
  - 不包含完整 `SKILL.md` 正文。
- `state/agent_state.py`
  - 保持现有 `LoopState`、`ToolRuntimeContext` 等运行状态。
  - 不把完整技能正文放入全局状态；完整正文只随工具结果进入当前对话。
- `tools_configs/base_configs.py`
  - 不新增独立的 `skill_configs.py`。
  - 在 `base_configs.py` 中直接定义 `SKILL_TOOLS`，保持基础工具 schema 的统一出口。
  - `SKILL_TOOLS` 第一阶段只提供一个工具：
    - `load_skill`
    - 入参：`name`
    - 作用：按技能名加载对应 `SKILL.md`。
  - 将 `SKILL_TOOLS` 合并进 `BASE_TOOLS`，让主 Agent 能看到 `load_skill`。
  - 不设计 `load_skill_file(path)`，避免模型直接传任意路径。
- `handlers/base_handlers.py`
  - 不新增独立的 `skill_handlers.py`。
  - 在 `base_handlers.py` 中直接实现 `handle_load_skill(args)`。
  - `handle_load_skill(args)` 调用 `SkillRegistry.load_skill(name)`。
  - 返回内容需要包含：
    - 技能名称。
    - 技能入口文件路径。
    - 完整或截断后的 `SKILL.md` 内容。
    - 如果发生截断，明确提示模型需要通过 `read_file` 读取相关引用文件。
  - 把 `"load_skill": handle_load_skill` 合并进 `BASE_HANDLERS`，让主 Agent 通过现有 dispatcher 分发。
- `tools_configs/subagent_configs.py`
  - 子 Agent 也需要具备技能加载能力。
  - 当 `ALLOW_SUBAGENT_LOAD_SKILL: true` 时，把 `load_skill` 加入 `SUBAGENT_AVAILABLE_TOOLS`。
  - 子 Agent 的 `load_skill` schema 可以复用 `base_configs.py` 中的同一份工具定义，避免主 Agent 和子 Agent 描述不一致。
  - 子 Agent 仍然不能看到 `task`，避免递归创建子 Agent。
  - 子 Agent 仍然不暴露 `todo`，避免污染父 Agent 计划。
- `handlers/subagent_handlers.py`
  - 当 `ALLOW_SUBAGENT_LOAD_SKILL: true` 时，把 `"load_skill": handle_load_skill` 加入 `SUBAGENT_HANDLERS`。
  - `handle_load_skill` 复用 `base_handlers.py` 中的同一个实现。
  - 子 Agent 调用 `load_skill` 仍然经过 `PreToolUse` / `PostToolUse` Hook 和权限检查。
- `managers/system_prompt_builder.py`
  - 负责组合最终 system prompt。
  - 基础提示词仍放在 `prompts/system_prompts.py`。
  - builder 只额外注入技能目录，不注入完整技能内容。
  - 同时支持主 Agent 和子 Agent：
    - `build_main_system_prompt(...)`：基于 `SYSTEM_WITH_TOOLS` 注入技能目录。
    - `build_subagent_system_prompt(...)`：基于 `SUBAGENT_SYSTEM_PROMPT` 注入同一份技能目录。
  - 子 Agent 看到的也只是技能目录，不是完整技能正文。
  - 目录格式建议：

```text
可用技能：
- docx：用于创建、读取、编辑 Word 文档。
- pdf：用于读取、分析、填写或转换 PDF。
- pptx：用于创建和编辑 PowerPoint。
- xlsx：用于处理 Excel 表格。
- frontend-design：用于高质量前端界面设计。
- web-access：用于搜索、抓取、浏览器访问等联网任务。

需要使用某个技能时，先调用 load_skill(name) 读取完整说明。
```

- `utils/config_handler.py`
  - 增加 `skill_config.yml` 的读取。
  - 提供默认配置，保证配置文件缺失时项目仍能启动。
- `configs/subagent_config.yml`
  - s07 起建议把 `load_skill` 加入默认 `ALLOWED_SUBAGENT_TOOLS`。
  - 子 Agent 是否最终可见 `load_skill` 同时受 `ALLOWED_SUBAGENT_TOOLS` 和 `ALLOW_SUBAGENT_LOAD_SKILL` 控制。
- `configs/permission_config.yml`
  - `allow` 中增加 `load_skill`。
  - `load_skill` 只允许读取 `skills/` 下的 `SKILL.md`，不需要用户审批。
- `agent_loop.py`
  - 通过 `system_prompt_builder` 间接使用全局 `SKILL_REGISTRY`。
  - `SKILL_REGISTRY` 在 `managers/skill_manager.py` 模块加载时扫描技能目录。
  - 构造 system prompt 时改用 `system_prompt_builder`。
  - Agent Loop 本身不感知具体有哪些技能，继续只负责模型调用、工具分发和 hook 执行。

运行流程：

```text
程序启动
  ↓
读取 skill_config.yml
  ↓
扫描 skills/*/SKILL.md
  ↓
解析 frontmatter，得到技能目录
  ↓
system prompt 只注入技能名和描述
  ↓
模型判断任务需要某个技能
  ↓
调用 load_skill(name)
  ↓
handler 读取对应 SKILL.md
  ↓
完整技能说明作为 tool_result 进入上下文
  ↓
模型根据技能说明继续使用 read_file/bash/write_file/edit_file 等工具
```

子 Agent 加载流程：

```text
父 Agent 调用 task
  ↓
子 Agent 启动
  ↓
根据 subagent_config.yml 过滤可见工具
  ↓
如果允许 load_skill，则子 Agent 工具列表包含 load_skill
  ↓
子 Agent system prompt 注入同一份技能目录摘要
  ↓
子 Agent 按需调用 load_skill(name)
  ↓
完整 SKILL.md 只进入子 Agent 自己的 messages
  ↓
父 Agent 最终只收到子 Agent 的结论，不继承子 Agent 加载过的完整技能正文
```

与已有模块的关系：

- 和 s04 Hook 的关系：
  - `load_skill` 仍然走 `PreToolUse` 和 `PostToolUse`。
  - 权限检查作为 `PreToolUse` hook 统一处理。
  - 大输出提醒可以在 `PostToolUse` 中提示技能内容过长。
- 和 s05 Todo 的关系：
  - 加载技能不等于创建计划。
  - 如果任务复杂，模型仍应先用 `todo` 拆分步骤，再按需加载技能。
- 和 s06 Subagent 的关系：
  - 主 Agent 和子 Agent 都可以使用 `load_skill`。
  - 子 Agent 加载到的完整 `SKILL.md` 只存在于子 Agent 自己的上下文。
  - 父 Agent 不会因为子 Agent 加载技能而自动继承完整技能正文。
  - 子 Agent 仍然不能调用 `task`，避免递归创建子 Agent。
  - 子 Agent 仍然不使用 `todo`，避免覆盖父 Agent 的计划。
- 和 s08 Context Compact 的关系：
  - s07 解决“不要提前放入上下文”。
  - s08 解决“已经进入上下文的内容如何压缩或移除”。

设计约束：

- system prompt 中只出现技能目录，不出现完整 `SKILL.md`。
- 主 Agent 和子 Agent 都只看到技能目录摘要。
- 技能名必须来自注册表，不能把用户传入的 `name` 当文件路径直接拼接。
- `load_skill` 不读取 `scripts/`、`reference.md`、`README.md` 等附加资源，只返回入口说明。
- 附加资源由技能说明指引模型后续按需读取。
- 技能扫描失败不能阻断主 Agent 启动，应记录日志并返回空目录。
- 技能目录的摘要需要有长度限制，防止某个 frontmatter 描述过长。
- 不新增 `skill_configs.py` 和 `skill_handlers.py`，避免工具定义和映射被拆得过散。
- 主 Agent 的 `load_skill` 放在 `base_configs.py` / `base_handlers.py`。
- 子 Agent 复用主 Agent 的 `load_skill` schema 和 handler，但可见性仍由 `subagent_configs.py` / `subagent_handlers.py` 控制。

验收：

- 启动日志能看到扫描到的技能数量。
- system prompt 中只能看到技能名和描述，看不到完整 `SKILL.md` 正文。
- 当任务涉及 Word、PDF、PPT、Excel、前端设计或联网访问时，模型能先调用 `load_skill`。
- 调用 `load_skill("docx")` 后，工具结果能返回 `skills/docx/SKILL.md` 的完整说明。
- 子 Agent 接到文档、表格、前端设计或联网类子任务时，也能调用 `load_skill`。
- 子 Agent 调用 `load_skill` 后，父 Agent 的 messages 不会自动出现完整技能正文。
- 调用不存在的技能名时，返回清晰错误和当前可用技能列表。
- `load_skill("../.env")` 这类路径穿越输入不能读取项目敏感文件。
- 主循环、权限、Hook、Todo、Subagent 的现有行为不受影响。

## 11. s08: Context Compact

主题：上下文总会满，要有办法腾地方。

目标：

- 支持当前 OpenAI Chat Completions messages 的上下文压缩。
- 通过 Hook 挂到 Agent Loop 上，不把压缩细节写进 `agent_loop.py`。
- 工具执行后先压缩单次大输出，避免超大结果直接进入 `state.messages`。
- 每轮模型调用前由 `BeforeModelCall` 做历史消息整理和必要的 LLM 摘要。
- 模型可调用 `compact(focus=...)` 主动登记压缩请求，下一轮模型调用前执行。
- 当模型 API 报上下文过长时，触发一次 reactive compact 后重试。
- 调用模型时通过 `max_tokens` 控制输出长度，降低上下文窗口被输出预算挤占的风险。

要完成什么：

- L1：`persist_tool_output` / `persist_large_tool_outputs`，把超大工具输出落盘。
- L2：`micro_compact_tool_results`，把较旧的工具结果替换为占位说明。
- L3：`snip_middle_messages`，裁剪对话中间不再相关的旧消息。
- L4：`compact_history`，调用模型把历史压缩成一条中文摘要消息。
- Manual compact：`compact` 工具只登记请求，不在当前 tool call 内立即改写 messages。
- Reactive compact：当模型调用因为上下文过长失败时，触发一次应急 L4 摘要。
- Transcript：每次 L4 / Reactive compact 前，把完整 messages 写入 `.transcripts/`，保留可追溯记录。

文件设计：

```text
configs/
└── compact_config.yml
state/
├── agent_state.py
├── hook_state.py
└── compact_state.py
hooks/
├── builtin_hooks.py
└── hook_manager.py
managers/
└── compact_manager.py
prompts/
└── compact_prompts.py
tools_configs/
└── base_configs.py
handlers/
└── base_handlers.py
utils/
└── token_counter.py
.task_outputs/
└── tool-results/
.transcripts/
```

实现内容：

- `configs/compact_config.yml`
  - `ENABLE_AUTO_COMPACT: true`：是否启用自动压缩。
  - `MAX_MESSAGES_BEFORE_SNIP: 20`：超过多少条消息后裁剪中间历史。
  - `KEEP_HEAD_MESSAGES: 3`：裁剪时保留开头多少条消息。
  - `KEEP_TAIL_MESSAGES: 45`：裁剪时保留最近多少条消息。
  - `KEEP_RECENT_TOOL_RESULTS: 4`：保留最近几个完整工具结果。
  - `LARGE_TOOL_OUTPUT_CHARS: 12000`：单条工具结果超过多少字符后落盘。
  - `TOOL_OUTPUT_PREVIEW_CHARS: 1200`：落盘后在上下文里保留多少字符预览。
  - `AUTO_COMPACT_TOKEN_THRESHOLD: 3000`：估算 token 超过阈值时触发 L4 摘要。
  - `MAX_REACTIVE_COMPACT_RETRIES: 1`：prompt-too-long 后最多应急压缩几次。
  - `MAX_SUMMARY_INPUT_CHARS: 30000`：生成摘要时最多提交多少字符的历史。
  - `MAX_OUTPUT_TOKENS: 2048`：主模型调用和 compact 摘要调用的输出 token 上限。
  - `ENABLE_SUBAGENT_LLM_COMPACT: false`：子 Agent 是否允许触发 L4 LLM 摘要。
  - `TRANSCRIPT_DIR: ".transcripts"`：完整历史保存目录。
  - `TOOL_OUTPUT_DIR: ".task_outputs/tool-results"`：大工具结果保存目录。
- `state/compact_state.py`
  - `CompactState`：
    - `has_compacted: bool`
    - `last_summary: str`
    - `last_transcript_path: str`
    - `reactive_retries: int`
    - `compacted_tool_outputs: dict`
    - `pending_manual_focus: str`
  - `PersistedToolOutput`：
    - `tool_call_id`
    - `path`
    - `original_chars`
    - `preview`
- `state/hook_state.py`
  - 现有 `HookContext` 已有 `messages`、`model_id`、`metadata` 字段。
  - s08 不新增 Hook 事件，在 `metadata` 中传入：
    - `client`
    - `compact_manager`
    - `subagent_depth`
    - `allow_subagent_llm_compact`
    - `tool_call_id`
  - `BeforeModelCall` 的 compact hook 直接原地修改 `context.messages`。
  - `PostToolUse` 的 compact hook 使用已有 `HookResult(updated_output=...)` 改写工具输出。
- `utils/token_counter.py`
  - `estimate_text_tokens(text)`：用字符数做保守 token 粗估。
  - `estimate_message_tokens(messages)`：把 messages 序列化后估算 token。
  - 当前实现不引入额外 tokenizer 依赖。
- `managers/compact_manager.py`
  - `CompactManager` 负责所有上下文压缩逻辑。
  - `request_manual_compact(focus)`：
    - 由 `compact` 工具调用。
    - 只写入 `state.pending_manual_focus`。
    - 返回普通 tool result，真正压缩放到下一轮 `BeforeModelCall`。
  - `pre_model_compact(messages, client, model_id, focus="", allow_llm=True)`：
    - 在每轮模型调用前执行。
    - 顺序固定：大工具结果落盘 → 旧工具结果占位 → 裁剪中间消息 → 必要时 LLM 摘要。
    - 如果存在 `pending_manual_focus`，即使 token 未超过阈值，也触发 L4。
    - 如果 `allow_llm=False`，只执行 L1/L2/L3，不执行 L4 摘要。
  - `persist_tool_output(output, tool_name, tool_call_id)`：
    - `PostToolUse` 阶段处理本次工具输出。
    - 超过 `LARGE_TOOL_OUTPUT_CHARS` 时写入 `.task_outputs/tool-results/`。
    - 返回 `<persisted-tool-output ...>` 占位内容。
  - `persist_large_tool_outputs(messages)`：
    - 针对当前项目的 OpenAI messages 结构处理 `{"role": "tool", "content": ...}`。
    - 超过阈值的 `tool` 消息写入 `.task_outputs/tool-results/`。
    - 原消息内容替换为 `<persisted-tool-output path="..." original_chars="...">` 加预览。
    - 这是兜底逻辑，用于处理历史遗留或绕过 `PostToolUse` 的大工具结果。
  - `micro_compact_tool_results(messages)`：
    - 保留最近 N 条完整 `role=tool` 消息。
    - 更旧的长工具结果替换为简短占位符。
    - 占位符要说明可以重新读取落盘文件或重新执行工具。
  - `snip_middle_messages(messages)`：
    - 消息过多时保留头部和尾部，中间替换为一条摘要占位消息。
    - 必须保护 OpenAI tool call 顺序：不能留下孤立的 `role=tool`，也不能删除 assistant tool_calls 后保留对应 tool result。
    - 裁剪后继续调用 `normalize_messages()` 做最终规范化。
  - `compact_history(messages, client, model_id, focus="")`：
    - 先调用 `write_transcript(messages)` 保存完整历史。
    - 再使用模型根据 `COMPACT_HISTORY_PROMPT` 生成摘要。
    - 用一条 `role=user` 摘要消息替换旧历史。
    - 摘要消息包含 transcript 路径和中文摘要。
  - `reactive_compact(messages, client, model_id)`：
    - 处理 API 返回上下文过长时的应急压缩。
    - 在重试次数内强制调用 `compact_history(...)`。
  - `write_transcript(messages)`：
    - 保存 JSONL transcript。
    - transcript 文件用于追溯，不默认重新注入 prompt。
- `hooks/builtin_hooks.py`
  - 新增 `compact_before_model_call_hook(context)`：
    - 绑定到 `BeforeModelCall`。
    - 从 `context.messages` 获取当前 messages。
    - 从 `context.metadata` 获取 `client`、`model_id`、`compact_manager`。
    - 根据 `subagent_depth` 和 `allow_subagent_llm_compact` 判断是否允许 L4。
    - 调用 `compact_manager.pre_model_compact(...)`，原地更新 `context.messages`。
  - 新增 `compact_post_tool_use_hook(context)`：
    - 绑定到 `PostToolUse`。
    - 对单次工具输出做快速检查。
    - 如果输出过大，提前落盘并通过 `updated_output` 返回占位内容。
    - 这样大输出在进入 `state.messages` 前就被压缩，减少下一轮上下文压力。
- `hooks/hook_manager.py`
  - 在 `register_builtin_hooks()` 中注册：
    - `BeforeModelCall -> todo_reminder_hook`
    - `BeforeModelCall -> compact_before_model_call_hook`
    - `BeforeModelCall -> log_before_model_call`
    - `PostToolUse -> log_post_tool_use`
    - `PostToolUse -> compact_post_tool_use_hook`
  - 当前顺序含义：
    - `todo_reminder_hook` 先注入计划提醒，compact 会把提醒纳入上下文预算。
    - `compact_before_model_call_hook` 再整理 messages。
    - `log_before_model_call` 最后记录压缩后的消息数量。
    - `log_post_tool_use` 先记录原始输出长度。
    - `compact_post_tool_use_hook` 再决定是否把大输出落盘。
- `prompts/compact_prompts.py`
  - `COMPACT_HISTORY_PROMPT`：要求模型输出中文摘要。
  - 摘要必须保留：
    - 当前用户目标。
    - 已完成事项。
    - 未完成事项。
    - 已读取或修改的关键文件。
    - 重要工具结果和结论。
    - 用户明确约束。
    - 当前 Todo 状态。
    - 已加载的 Skill 名称及其关键指令。
    - 子 Agent 返回的关键结论。
  - 摘要不能编造未发生的工具结果。
- `tools_configs/base_configs.py`
  - 不新增独立的 `compact_configs.py`。
  - 在 `base_configs.py` 中定义 `COMPACT_TOOLS`。
  - `compact` 参数：
    - `focus`：可选，说明这次压缩应该重点保留什么。
  - 将 `COMPACT_TOOLS` 合并进 `BASE_TOOLS`。
- `handlers/base_handlers.py`
  - 不新增独立的 `compact_handlers.py`。
  - 新增 `handle_compact(args)`。
  - handler 调用 `COMPACT_MANAGER.request_manual_compact(focus)`。
  - `compact` 和普通工具一样返回字符串，不在 handler 内直接改写 `state.messages`。
- `state/agent_state.py`
  - `ToolRuntimeContext` 增加 `compact_manager`，供子 Agent 运行时复用同一个 compact 管理器。
- `agent_loop.py`
  - 不直接写分层压缩流程。
  - 使用全局 `COMPACT_MANAGER`，通过 `HookContext.metadata` 传给 `BeforeModelCall` hook。
  - 继续在每轮模型调用前运行已有 `BeforeModelCall` hook。
  - Hook 运行后再执行 `normalize_messages()`。
  - `client.chat.completions.create(...)` 增加 `max_tokens=_max_output_tokens()`。
  - 调用模型时捕获上下文过长错误，触发 `reactive_compact()` 后重试一次。
- `subagents/task_subagent.py`
  - 子 Agent 也运行 `BeforeModelCall` compact hook。
  - 子 Agent 默认只启用低成本压缩：
    - L1 大工具结果落盘。
    - L2 旧工具结果占位。
    - L3 消息数裁剪。
  - `ENABLE_SUBAGENT_LLM_COMPACT: false` 时，子 Agent 不触发 L4 摘要，避免额外消耗模型调用。
  - 如需允许子 Agent 进行 L4，可把 `ENABLE_SUBAGENT_LLM_COMPACT` 改为 `true`。
- `configs/permission_config.yml`
  - `allow` 中增加 `compact`。
  - `compact` 不直接读写用户文件，但会写 `.transcripts/` 和 `.task_outputs/`，属于 harness 内部管理目录，不需要用户审批。

Context Compact 的执行流程：

```text
1. 进入新一轮 Agent Loop。

compact_before_model_call_hook（包含阶段2到7）
2. 阶段：调用模型前，触发 `BeforeModelCall`。
   方法：`compact_before_model_call_hook`
   作用：统一检查当前 `state.messages` 是否需要压缩。

3. 阶段：`BeforeModelCall` 内部，先处理历史遗留的大工具结果。
   触发条件：历史 `messages` 中存在超过 `LARGE_TOOL_OUTPUT_CHARS` 的 `role=tool` 消息。
   压缩方法：`persist_large_tool_outputs(messages)`
   所属级别：L1，大工具结果落盘。
   执行结果：
   - 完整工具输出写入 `.task_outputs/tool-results/`。
   - 原 `tool` 消息替换为落盘路径、原始长度和预览。
   - 这是兜底压缩，用于处理未在 `PostToolUse` 阶段被压缩的大输出。

4. 阶段：`BeforeModelCall` 内部，再处理旧工具结果。
   触发条件：`role=tool` 消息数量超过 `KEEP_RECENT_TOOL_RESULTS`。
   压缩方法：`micro_compact_tool_results(messages)`
   所属级别：L2，旧工具结果占位。
   执行结果：
   - 保留最近 N 条完整工具结果。
   - 更旧的长工具结果替换为占位说明。

5. 阶段：`BeforeModelCall` 内部，再处理过多历史消息。
   触发条件：`messages` 总条数超过 `MAX_MESSAGES_BEFORE_SNIP`，且 `KEEP_HEAD_MESSAGES + KEEP_TAIL_MESSAGES < len(messages)`。
   压缩方法：`snip_middle_messages(messages)`
   所属级别：L3，中间历史裁剪。
   执行结果：
   - 保留开头目标消息和最近上下文。
   - 中间历史替换为一条裁剪说明。
   - 裁剪时保护 assistant tool_calls / role=tool 顺序。

6. 阶段：`BeforeModelCall` 内部，最后检查整体上下文长度。
   触发条件：`estimate_message_tokens(messages)` 超过 `AUTO_COMPACT_TOKEN_THRESHOLD`，且当前上下文允许 L4。
   压缩方法：`compact_history(messages, client, model_id, focus)`
   所属级别：L4，LLM 历史摘要。
   执行结果：
   - 先执行 `write_transcript(messages)` 保存完整历史。
   - 再调用模型生成中文摘要。
   - 用一条摘要消息替换旧历史。

7. 阶段：模型主动请求压缩后的下一轮 `BeforeModelCall`。
   触发条件：上一轮模型调用过 `compact(focus=...)`，产生 `pending_manual_focus`。
   压缩方法：`compact_history(messages, client, model_id, focus)`
   所属级别：L4，手动触发的 LLM 历史摘要。
   执行结果：
   - 即使 token 未超过阈值，也写 transcript 并生成摘要。
   - 摘要会按 `focus` 重点保留信息。

8. 阶段：`BeforeModelCall` 压缩完成后。
   方法：`normalize_messages(...)`
   作用：清理内部字段，保证 OpenAI tool_calls / role=tool 顺序合法。
   注意：这不是压缩级别，只是模型调用前的消息规范化。

9. 阶段：调用模型。
   方法：`client.chat.completions.create(...)`
   作用：使用压缩后的 messages 请求模型，并通过 `max_tokens` 限制输出预算。

10. 阶段：模型返回工具调用后，dispatcher 执行真实工具 handler。
    方法：普通工具执行。
    注意：此时还没有压缩工具输出。

compact_post_tool_use_hook（包含阶段11到12）
11. 阶段：工具执行后，触发 `PostToolUse`。
    触发条件：本次工具输出超过 `LARGE_TOOL_OUTPUT_CHARS`。
    压缩方法：`persist_tool_output(...)`
    所属级别：L1，单次工具输出即时落盘。
    执行结果：
    - 完整输出写入 `.task_outputs/tool-results/`。
    - hook 返回 `HookResult(updated_output=占位内容)`。
    - dispatcher 将压缩后的输出写入 `state.messages`。

12. 阶段：工具执行后，触发 `PostToolUse`。
    触发条件：本次工具输出不超过 `LARGE_TOOL_OUTPUT_CHARS`。
    压缩方法：无。
    所属级别：无。
    执行结果：工具输出原样写入 `state.messages`。

13. 阶段：模型主动调用 `compact(focus=...)` 工具。
    触发条件：模型认为当前上下文需要阶段性压缩。
    压缩方法：`request_manual_compact(focus)`
    所属级别：请求阶段，不直接压缩；下一轮进入 L4。
    执行结果：
    - 当前 tool call 只返回普通 tool result。
    - 不立即改写当前 `messages`。
    - 下一轮 `BeforeModelCall` 才执行 L4 `compact_history`。
    - 这样不会破坏当前 assistant tool_calls 与 role=tool 结果的对应关系。

14. 阶段：模型调用失败后的异常恢复。
    触发条件：`client.chat.completions.create(...)` 抛出 context length / prompt too long 类错误。
    压缩方法：`reactive_compact(messages, client, model_id)`
    所属级别：Reactive，应急 L4 摘要。
    执行结果：
    - 保存 transcript。
    - 强制执行 `compact_history`。
    - 未超过 `MAX_REACTIVE_COMPACT_RETRIES` 时回到下一轮重试。
    - 超过重试上限后抛出错误，不无限循环。
```

顺序原因：

- `PostToolUse` 先压缩单次工具输出，是为了让大结果尽早落盘，避免原始大文本进入 `state.messages`。
- `BeforeModelCall` 中再次执行 `persist_large_tool_outputs` 是兜底，处理历史遗留或绕过 PostToolUse 的大 `tool` 消息。
- `micro_compact_tool_results` 放在大输出落盘之后，因为大输出需要先保存完整内容，再把旧结果替换成占位。
- `snip_middle_messages` 放在工具结果处理之后，因为裁剪消息前应先减少单条消息体积；如果当前消息数还没有超过头尾保留数量之和，代码会跳过裁剪。
- `compact_history` 最后执行，因为它需要额外模型调用，成本最高。
- 手动 `compact` 不在当前 tool call 内立即改写 messages，是为了避免破坏 OpenAI 的 assistant tool_calls / tool result 对应关系。
- Reactive compact 只处理异常路径，避免正常循环里混入错误恢复逻辑。

Hook 化设计原则：

- `agent_loop.py` 只保留生命周期事件：
  - `SessionStart`
  - `BeforeModelCall`
  - `AfterModelCall`
  - `PreToolUse`
  - `PostToolUse`
  - `Stop`
- Context Compact 作为横切能力挂在 Hook 上，不进入主循环主体。
- `compact_before_model_call_hook` 负责“调用模型前上下文是否该变小”。
- `compact_post_tool_use_hook` 负责“工具输出进入 messages 前是否该变小”。
- `compact` 工具负责“模型主动请求压缩”。
- Reactive compact 是异常恢复逻辑，当前放在 `agent_loop.py` 的模型调用异常分支中。

验收：

- 大工具输出不会无限塞进 messages，而是落盘到 `.task_outputs/tool-results/`。
- `messages` 中的落盘占位符包含路径、原始长度和预览。
- 旧 `role=tool` 消息会被替换成占位说明。
- 消息过多时可以裁剪中间历史，但不会破坏 assistant tool_calls / tool result 顺序。
- 上下文超过阈值时能自动调用模型生成中文摘要。
- 每次 L4 或 Reactive compact 前都会写 transcript。
- 模型可以主动调用 `compact`。
- `compact` 工具当前轮只登记请求，下一轮 `BeforeModelCall` 再真正压缩。
- 主 Agent compact 后仍保留当前目标、Todo、已加载技能、子 Agent 结论和关键文件。
- 子 Agent 默认不触发 L4 摘要，只做低成本压缩；配置开启后才允许 L4。
- API 上下文过长时会触发一次 reactive compact，超过重试上限后返回明确错误。

## 12. s09: Memory

主题：压缩会丢细节，要有一层不丢的。

目标：

- 在 s08 Context Compact 之外增加长期 Memory，解决“压缩摘要会丢细节、重启会话会丢上下文”的问题。
- 采用文件系统记忆：`MEMORY.md` 只做索引，具体记忆拆成独立 Markdown 文件。
- 区分 private / team 两种作用域，避免把个人偏好误写成项目共识。
- 区分 `user`、`feedback`、`project`、`reference` 四类记忆。
- 支持三条路径：
  - 启动和模型调用前加载记忆索引。
  - 根据当前任务用 LLM side-query 按需召回相关记忆正文。
  - 模型主动调用工具保存或删除长期记忆。
- 支持 Stop 阶段的自动提取和低频 Dream 整理，但不把这些流程写进 `agent_loop.py`。

要完成什么：

- `MEMORY.md` 索引：
  - private 和 team 各自有独立索引。
  - 索引只保存一行摘要和文件链接，不保存完整内容。
- 具体记忆文件：
  - Markdown + YAML frontmatter。
  - frontmatter 包含 `name`、`description`、`type`、`scope`、`updated_at`。
- Memory 召回：
  - system prompt 中注入索引。
  - `BeforeModelCall` 把最近对话和记忆目录交给 LLM side-query，选择最多 5 个相关文件名。
  - 读取选中文件正文，作为临时 `[Memory context]` user message 注入当前上下文。
  - LLM 正常返回空数组时不注入记忆；只有 side-query 调用失败时才退回关键词匹配。
- Memory 写入：
  - `save_memory` 工具用于模型主动保存长期记忆。
  - `forget_memory` 工具用于删除或废弃过时/错误记忆。
  - 用户明确说“记住”时优先主动写入。
- Memory 提取：
  - `Stop` Hook 在一轮任务结束后分析最近对话，提取值得保存的长期信息。
  - 自动提取必须检查已有记忆，优先更新，避免重复写入。
- Dream 整理：
  - 第一版只实现低频门控和索引重建。
  - 达到文件数量阈值并且锁未过期时，写 `.memory/.dream-lock`，重建 private/team 索引。
  - LLM 合并、去重、修剪作为后续增强，不在当前代码中执行。
- 和 s08 的关系：
  - Compact 负责当前会话压缩续接。
  - Memory 负责跨压缩、跨会话仍然有价值的长期信息。

文件设计：

```text
configs/
└── memory_config.yml
state/
└── memory_state.py
managers/
└── memory_manager.py
prompts/
└── memory_prompts.py
tools_configs/
└── base_configs.py
handlers/
└── base_handlers.py
hooks/
├── builtin_hooks.py
└── hook_manager.py
.memory/
├── private/
│   ├── MEMORY.md
│   └── *.md
└── team/
    ├── MEMORY.md
    └── *.md
```

实现内容：

- `configs/memory_config.yml`
  - `ENABLE_MEMORY: true`：是否启用长期记忆。
  - `PRIVATE_MEMORY_DIR: ".memory/private"`：私有记忆目录。
  - `TEAM_MEMORY_DIR: ".memory/team"`：团队记忆目录。
  - `MAX_INDEX_LINES: 200`：每个 `MEMORY.md` 最多注入多少行索引。
  - `MAX_MEMORY_FILES: 200`：扫描记忆文件数量上限。
  - `MAX_RELEVANT_MEMORIES: 5`：每轮最多注入几条完整记忆。
  - `MAX_MEMORY_FILE_CHARS: 4096`：单个记忆正文注入上限。
  - `MAX_TOTAL_MEMORY_CHARS: 60000`：单轮记忆注入总预算。
  - `AUTO_EXTRACT_MEMORY: true`：是否在 Stop 阶段自动提取记忆。
  - `EXTRACT_RECENT_MESSAGES: 12`：自动提取时查看最近多少条消息。
  - `DREAM_ENABLED: true`：是否启用整理。
  - `DREAM_MIN_FILES: 10`：记忆文件数达到多少后允许整理。
  - `DREAM_MIN_INTERVAL_HOURS: 24`：两次整理之间的最小间隔。
  - `MEMORY_LOCK_TTL_MINUTES: 60`：Dream 锁过期时间。
- `state/memory_state.py`
  - `MemoryItem`：
    - `name`
    - `description`
    - `type`
    - `scope`
    - `path`
    - `updated_at`
  - `MemorySelection`：
    - `items`
    - `reason`
    - `source`
  - `MemoryState`：
    - `loaded_index_text`
    - `loaded_memory_paths`
    - `last_dream_at`
    - `saved_this_turn`
- `prompts/memory_prompts.py`
  - `MEMORY_SYSTEM_RULES`：
    - 说明 Memory 的用途、边界和使用规则。
    - 明确 Memory 可能过期，使用前要结合当前项目状态验证。
    - 明确不要把临时任务状态、API Key、凭据、Git 历史、可从代码读取的信息写入 Memory。
  - `MEMORY_RELEVANCE_PROMPT`：
    - 根据当前请求、最近对话和候选记忆目录选择相关记忆。
    - 要求只返回 JSON 字符串数组，数组元素必须是候选目录中的 filename。
    - 最多选择 `MAX_RELEVANT_MEMORIES` 条，不确定就返回 `[]`。
  - `MEMORY_EXTRACT_PROMPT`：
    - 从最近对话中提取长期有效信息。
    - 要求返回 JSON 数组：`name`、`scope`、`type`、`description`、`content`。
  - `MEMORY_DREAM_PROMPT`：
    - 合并重复记忆。
    - 删除过时或冲突记忆。
    - 缩短索引描述。
    - 当前代码暂未调用，保留给后续 LLM Dream。
- `managers/memory_manager.py`
  - `ensure_dirs()`：
    - 创建 `.memory/private` 和 `.memory/team`。
    - 初始化两个 `MEMORY.md`。
  - `scan_memory(scope=None)`：
    - 扫描记忆目录。
    - 排除 `MEMORY.md`。
    - 读取 frontmatter。
    - 按 `updated_at` 或 mtime 排序。
  - `load_index_prompt()`：
    - 读取 private/team 两个 `MEMORY.md`。
    - 返回可注入 system prompt 的索引文本。
    - 索引超过 `MAX_INDEX_LINES` 时截断。
  - `select_relevant_memories(messages, client=None, model_id=None)`：
    - 根据最近请求和候选记忆目录选择相关记忆。
    - 传入 `client` 和 `model_id` 时优先调用 `_select_relevant_memories_with_llm(...)`。
    - LLM side-query 返回 filename 数组后，只接受真实存在的候选文件名。
    - 如果 LLM 正常返回 `[]`，本轮不注入记忆正文。
    - 只有 side-query 调用异常或解析失败时，才降级到关键词匹配。
  - `_select_relevant_memories_with_llm(messages, items, client, model_id)`：
    - 构造候选目录：`filename`、`scope`、`type`、`name`、`description`。
    - 使用 `MEMORY_RELEVANCE_PROMPT` 调用模型。
    - 受 `MEMORY_RELEVANCE_MAX_TOKENS` 控制输出长度。
  - `_select_relevant_memories_by_keyword(messages, items)`：
    - 作为 side-query 失败后的兜底。
    - 根据最近对话和 `name/description/type/scope` 做关键词匹配。
  - `load_relevant_memory_prompt(selection)`：
    - 读取选中的记忆正文。
    - 限制单文件和总字符预算。
    - 返回一条可注入 `messages` 的中文 Memory context。
  - `save_memory(name, scope, type, description, content)`：
    - 写入独立 Markdown 文件。
    - scope 只能是 `private` 或 `team`。
    - type 只能是 `user`、`feedback`、`project`、`reference`。
    - 自动生成安全 slug 文件名。
    - 写入后重建对应 `MEMORY.md`。
  - `forget_memory(name_or_path, scope, reason="")`：
    - 删除或归档指定记忆。
    - 第一版可以直接删除并重建索引。
  - `rebuild_index(scope)`：
    - 读取所有记忆 frontmatter。
    - 每条索引一行：`- [name](file.md) — description`。
    - `MEMORY.md` 不保存完整记忆正文。
  - `extract_memories(messages, client, model_id)`：
    - Stop 阶段自动运行。
    - 只分析最近 `EXTRACT_RECENT_MESSAGES` 条消息。
    - 先读取已有记忆摘要，避免重复写入。
    - 只保存未来仍有价值的信息。
  - `dream(client, model_id)`：
    - 达到 `DREAM_MIN_FILES` 后执行。
    - 使用 `.memory/.dream-lock` 防止并发整理。
    - 当前只重建 private/team 索引并更新锁时间。
    - `DREAM_MIN_INTERVAL_HOURS` 已在配置中保留，但当前代码实际通过 `MEMORY_LOCK_TTL_MINUTES` 控制锁过期。
- `tools_configs/base_configs.py`
  - 不新增 `memory_configs.py`。
  - 在 `base_configs.py` 中增加 `MEMORY_TOOLS`，再合并进 `BASE_TOOLS`。
  - `save_memory` 参数：
    - `name`
    - `scope`: `private | team`
    - `type`: `user | feedback | project | reference`
    - `description`
    - `content`
  - `forget_memory` 参数：
    - `name_or_path`
    - `scope`
    - `reason`
- `handlers/base_handlers.py`
  - 不新增 `memory_handlers.py`。
  - 新增：
    - `handle_save_memory(args)`
    - `handle_forget_memory(args)`
  - handler 调用全局 `MEMORY_MANAGER`。
  - 工具返回中文结果，例如：
    - `已保存 private/user memory: xxx`
    - `已删除 team/project memory: xxx`
- `hooks/builtin_hooks.py`
  - 新增 `memory_before_model_call_hook(context)`：
    - 绑定到 `BeforeModelCall`。
    - 从 `context.metadata` 读取 `client`，结合 `context.model_id` 执行 LLM side-query 召回。
    - 注入相关记忆正文。
    - 应放在 compact 前，确保 Memory 注入也参与 s08 的上下文预算。
    - 子 Agent 默认可读取 Memory 索引和相关记忆，但不自动写入 Memory。
  - 新增 `memory_stop_extract_hook(context)`：
    - 绑定到 `Stop`。
    - 如果本轮没有主动调用 `save_memory`，则尝试自动提取。
    - 提取后可触发低频 Dream。
    - 当前实现是同步执行，不是后台 fire-and-forget。
  - 可选 `memory_session_start_hook(context)`：
    - 绑定到 `SessionStart`。
    - 初始化目录、索引和运行时状态。
- `hooks/hook_manager.py`
  - 注册顺序建议：
    - `SessionStart -> memory_session_start_hook`
    - `BeforeModelCall -> memory_before_model_call_hook`
    - `BeforeModelCall -> todo_reminder_hook`
    - `BeforeModelCall -> compact_before_model_call_hook`
    - `BeforeModelCall -> log_before_model_call`
    - `Stop -> memory_stop_extract_hook`
  - 顺序原因：
    - Memory 先注入，再由 Todo reminder 补充当前计划。
    - Compact 最后整理所有即将进入模型的上下文。
- `managers/system_prompt_builder.py`
  - 启动或每轮模型调用前，把 `MEMORY_SYSTEM_RULES` 和 `load_index_prompt()` 加入 system prompt。
  - 只注入索引，不注入全部正文。
- `.memory/private/`
  - 保存用户私有记忆。
  - 典型内容：
    - 用户身份、背景、偏好。
    - 用户对回答风格、协作方式的要求。
    - 用户对 Agent 行为的个人反馈。
- `.memory/team/`
  - 保存项目共享记忆。
  - 典型内容：
    - 项目背景。
    - 团队共同约定。
    - 外部系统入口。
    - 重要项目决策。

Memory 类型和作用域：

```text
user:
  scope: always private
  内容: 用户身份、技术背景、偏好、协作方式。

feedback:
  scope: 默认 private；只有明确是项目级规则时才用 team。
  内容: 用户对 Agent 工作方式的纠正或确认。
  格式: 规则 + Why + How to apply。

project:
  scope: private 或 team，但偏向 team。
  内容: 项目目标、背景、决策、截止时间、外部约束。
  要求: 相对日期必须转成绝对日期。

reference:
  scope: 通常 team。
  内容: 外部系统入口和查找线索，不保存外部系统完整内容。
```

不应该保存到 Memory 的内容：

- 可通过读取当前代码得到的信息：
  - 代码结构。
  - 文件路径。
  - 当前目录结构。
  - 普通编码模式。
- Git 已经能回答的信息：
  - 近期提交。
  - 谁改了什么。
  - `git log` / `git blame` 可查的事实。
- 临时任务状态：
  - 当前 Todo。
  - 当前计划步骤。
  - 本轮还没完成的短期进度。
- 调试 recipe：
  - 某次 bug 的具体修复过程。
  - 只对当前代码版本成立的排查步骤。
- 敏感数据：
  - API Key。
  - token。
  - 密码。
  - 用户凭据。
- 已经写在项目文档里的稳定规则：
  - 如果 `README`、`CLAUDE.md` 或项目文档已经明确记录，不重复写 Memory。

Memory 写入格式：

```markdown
---
name: user-prefers-concise-code-review
description: 用户希望代码审查优先列出问题，避免冗长总结
type: feedback
scope: private
updated_at: 2026-07-05T12:00:00+08:00
---

用户希望代码审查时先列问题和风险。

**Why:** 用户能直接看 diff，不需要重复说明显而易见的改动。
**How to apply:** review 类请求中，优先输出发现的问题、证据和影响；没有问题时再简短说明测试缺口。
```

Memory 加载流程：

```text
1. SessionStart
   - ensure_dirs()
   - 确保 private/team 的 MEMORY.md 存在。

2. 构建 system prompt
   - 注入 MEMORY_SYSTEM_RULES。
   - 注入 private/team 的 MEMORY.md 索引。
   - 不注入所有记忆正文。

3. BeforeModelCall
   - memory_before_model_call_hook 根据当前请求和候选目录执行 LLM side-query。
   - side-query 返回最多 MAX_RELEVANT_MEMORIES 个 filename。
   - 读取最多 MAX_RELEVANT_MEMORIES 条正文。
   - 将正文作为一条 Memory context 追加到 messages。
   - 如果 side-query 正常返回 []，本轮不注入正文。
   - 如果 side-query 失败，回退关键词匹配。
   - 之后再进入 Todo reminder 和 Context Compact。

4. 模型调用
   - 模型可以使用已注入的相关记忆。
   - 如果用户明确要求记住，可以调用 save_memory。
   - 如果用户要求忘记，可以调用 forget_memory。

5. Stop
   - memory_stop_extract_hook 分析最近对话。
   - 若发现长期有效的新信息，调用 extract_memories。
   - 如果达到 Dream 门控，执行 dream 重建索引。
```

Memory 与权限：

- `save_memory` 和 `forget_memory` 只允许操作 `.memory/private` 和 `.memory/team`。
- Memory 工具不允许写入项目源码、`.env`、`configs/` 或其他业务目录。
- `forget_memory` 删除前建议走普通工具权限管线；第一版可对 `.memory/` 内删除放行。
- 自动提取阶段不得调用任意工具，只能通过 `MemoryManager` 写 Memory 目录。

和现有模块的关系：

- 和 `system_prompt_builder.py`：
  - Memory 索引属于 system prompt 的动态 section。
  - 相关记忆正文属于当前轮上下文，不直接写进 system prompt。
- 和 `compact_manager.py`：
  - Memory 注入发生在 compact 前。
  - 如果记忆正文过长，compact 可以继续压缩普通 messages。
  - Compact 摘要不替代长期 Memory。
- 和 `skill_manager.py`：
  - Skill 是按能力加载说明。
  - Memory 是按用户/项目长期事实加载上下文。
  - 两者都采用“索引常驻、正文按需”的思想。
- 和 `todo_manager.py`：
  - Todo 是当前任务进度，不写长期 Memory。
  - 如果某个计划背后的项目决策长期有效，才可能写成 project memory。
- 和 `subagents/task_subagent.py`：
  - 子 Agent 默认可以读取相关 Memory。
  - 子 Agent 默认不自动提取或写入 Memory，避免子任务噪声污染长期记忆。
  - 如果需要允许子 Agent 写 Memory，应通过配置单独开启。

验收：

- 启动后自动创建 `.memory/private/MEMORY.md` 和 `.memory/team/MEMORY.md`。
- system prompt 中能看到 Memory 使用规则和索引摘要。
- 模型能调用 `save_memory` 保存 private/team 记忆。
- 保存后对应 `MEMORY.md` 自动重建，索引只包含链接和短描述。
- 重启后 Memory 索引仍能注入 prompt。
- 当前请求与某条记忆相关时，`BeforeModelCall` 能注入该记忆正文。
- 相关记忆召回优先由 LLM side-query 选择 filename，最多注入 5 条。
- 用户要求“忘记”时，模型能调用 `forget_memory` 删除对应记忆并重建索引。
- Stop 阶段能从最近对话中提取长期有效信息，但不会保存临时 Todo 或敏感信息。
- Dream 达到门控后能重建索引；LLM 合并重复记忆留作后续增强。
- 子 Agent 可以读取相关 Memory，但默认不会写 Memory。
- s08 Context Compact 正常工作，不会因为 Memory 注入破坏 messages 格式。

## 13. s10: System Prompt

主题：运行时组装，不硬编码。

目标：

- 将当前 `system_prompts.py` 中的大段字符串，升级为“分段 + 运行时组装 + 稳定顺序 + 缓存”的 System Prompt 系统。
- 主 Agent 和子 Agent 都通过同一个 builder 组装 system prompt，但使用不同的 section 集合。
- system prompt 只放稳定规则、工具摘要、Skill 目录、Memory 索引、项目上下文；相关 Memory 正文仍由 s09 的 `BeforeModelCall` 注入 messages。
- section 是否加载由真实运行状态决定，例如工具是否启用、Memory 是否开启、项目是否存在 `CLAUDE.md`，不要靠用户消息关键词猜测。
- 避免在 `agent_loop.py` 和 `task_subagent.py` 中硬编码 prompt 拼接逻辑。

要完成什么：

- 建立统一的 `SystemPromptBuilder`。
- 把 prompt 拆成可维护 section。
- 为主 Agent 和子 Agent 定义不同的 section profile。
- 自动注入工作目录、工具摘要、Skill 目录、Memory 索引、项目指令文件、动态运行上下文。
- 支持简单缓存：当 prompt context 没变时，直接复用上次组装结果。
- 保持 s07 Skill Loading 和 s09 Memory 的设计原则：
  - Skill 只注入目录，不注入完整 `SKILL.md`。
  - Memory 只注入索引，不注入全部正文。
- 为后续 s11 Error Recovery、s12 Task、s16 Team、s20 MCP 预留 section 扩展点。

文件设计：

```text
configs/
└── prompt_config.yml
state/
└── prompt_state.py
prompts/
├── system_prompts.py
├── subagent_prompts.py
├── memory_prompts.py
├── prompt_sections.py
└── sections.py
managers/
└── system_prompt_builder.py
```

实现内容：

- `configs/prompt_config.yml`
  - `ENABLE_PROMPT_CACHE: true`：是否启用字符串组装缓存。
  - `INJECT_TOOL_SUMMARY: true`：是否把工具摘要注入 system prompt。
  - `INJECT_SKILL_CATALOG: true`：是否注入 Skill 目录；该字段可继续兼容 `skill_config.yml`。
  - `INJECT_MEMORY_INDEX: true`：是否注入 Memory 索引；实际还要看 `memory_config.ENABLE_MEMORY`。
  - `INJECT_PROJECT_INSTRUCTIONS: true`：是否读取项目指令文件。
  - `PROJECT_INSTRUCTION_FILES`：
    - `CLAUDE.md`
    - `.claude/CLAUDE.md`
    - `AGENTS.md`
  - `MAX_PROJECT_INSTRUCTION_CHARS: 12000`
  - `INJECT_RUNTIME_CONTEXT: true`
  - `STATIC_DYNAMIC_BOUNDARY: "<SYSTEM_PROMPT_DYNAMIC_BOUNDARY>"`
  - `DEBUG_PROMPT_SECTIONS: false`
- `state/prompt_state.py`
  - `PromptSection`：
    - `name`
    - `content`
    - `dynamic: bool`
  - `SystemPromptContext`：
    - `workdir`
    - `agent_type`: `main | subagent`
    - `enabled_tools`
    - `skill_catalog`
    - `memory_index`
    - `project_instructions`
    - `runtime_context`
  - `PromptBuildResult`：
    - `text`
    - `section_names`
    - `cache_hit`
- `prompts/system_prompts.py`
  - 保留核心身份和通用规则，但不要继续承担所有动态拼接。
  - 建议拆出：
    - `MAIN_IDENTITY_SECTION`
    - `TOOL_USE_RULES_SECTION`
    - `PLANNING_RULES_SECTION`
    - `RESPONSE_STYLE_SECTION`
  - 当前已有 `SYSTEM_WITH_TOOLS` 可作为迁移起点，后续逐步拆分。
- `prompts/subagent_prompts.py`
  - 保留子 Agent 专用身份、上下文隔离和返回格式规则。
  - 建议拆出：
    - `SUBAGENT_IDENTITY_SECTION`
    - `SUBAGENT_CONTEXT_RULES_SECTION`
    - `SUBAGENT_RESULT_RULES_SECTION`
- `prompts/prompt_sections.py`
  - 新增 section 名称和顺序定义。
  - 主 Agent 推荐顺序：
    1. `identity`
    2. `workspace`
    3. `tool_rules`
    4. `planning_rules`
    5. `permission_rules`
    6. `skills_index`
    7. `memory_rules_and_index`
    8. `project_instructions`
    9. `runtime_context`
    10. `response_style`
  - 子 Agent 推荐顺序：
    1. `subagent_identity`
    2. `workspace`
    3. `subagent_context_rules`
    4. `tool_rules`
    5. `skills_index`
    6. `memory_rules_and_index`
    7. `project_instructions`
    8. `runtime_context`
    9. `subagent_result_rules`
  - 标记哪些 section 是静态，哪些是动态。
- `prompts/sections.py`
  - 如果保留该文件，用于集中导出 section 常量。
  - 也可以让它只做兼容层，后续统一迁移到 `prompt_sections.py`。
- `managers/system_prompt_builder.py`
  - 当前已有：
    - `build_main_system_prompt(workdir)`
    - `build_subagent_system_prompt(workdir)`
    - `_skill_catalog_prompt()`
    - `_memory_index_prompt()`
  - s10 在此基础上扩展，不新增第二套 builder。
  - 新增或重构为：
    - `build_main_system_prompt(workdir, runtime_context=None)`
    - `build_subagent_system_prompt(workdir, runtime_context=None)`
    - `assemble_system_prompt(context: SystemPromptContext) -> PromptBuildResult`
    - `get_system_prompt(context: SystemPromptContext) -> str`
    - `_build_identity_section(context)`
    - `_build_workspace_section(context)`
    - `_build_tool_rules_section(context)`
    - `_build_tool_summary_section(context)`
    - `_build_skill_catalog_section(context)`
    - `_build_memory_index_section(context)`
    - `_build_project_instructions_section(context)`
    - `_build_runtime_context_section(context)`
    - `_split_static_dynamic_sections(sections)`
  - 缓存规则：
    - 使用 `json.dumps(context, sort_keys=True, ensure_ascii=False, default=str)` 生成稳定 cache key。
    - 不使用 Python `hash()`，避免进程随机化。
    - 只缓存最终字符串，第一版不实现 API 级 prompt cache。
  - 静态 / 动态边界：
    - 可以用 `STATIC_DYNAMIC_BOUNDARY` 在输出文本中分隔稳定 section 和动态 section。
    - 当前 OpenAI Chat Completions 仍只传一个 system message；边界主要用于调试和未来接入 API prompt cache。
  - 工具摘要：
    - 从 `tools_configs.BASE_TOOLS` 读取工具名和 description。
    - 不把完整 JSON schema 塞进 system prompt，因为 `tools=BASE_TOOLS` 已经传给模型。
    - 摘要用于告诉模型“什么时候用哪个工具”。
  - Skill 目录：
    - 继续使用 `SKILL_REGISTRY.list_catalog()`。
    - 只注入技能名和简短描述。
    - 完整技能说明仍通过 `load_skill(name)` 工具加载。
  - Memory 索引：
    - 继续调用 `MEMORY_MANAGER.load_index_prompt()`。
    - 只注入 `MEMORY.md` 索引和 `MEMORY_SYSTEM_RULES`。
    - 相关 Memory 正文仍由 `memory_before_model_call_hook` 注入 `[Memory context]`。
  - 项目指令文件：
    - 按 `PROJECT_INSTRUCTION_FILES` 顺序查找。
    - 只读取当前工作区内文件。
    - 多个文件都存在时按顺序拼接，并受 `MAX_PROJECT_INSTRUCTION_CHARS` 限制。
    - 这类内容属于项目级动态上下文，不写进 Memory。
  - runtime context：
    - 注入当前工作目录。
    - 注入 Agent 类型：主 Agent 或子 Agent。
    - 注入当前日期时间，必要时使用绝对日期。
    - 注入可选运行态标记，例如 subagent mode、已启用能力开关。
- `agent_loop.py`
  - 仍只调用 `build_main_system_prompt(str(WORKDIR))` 或新签名。
  - 不在主循环里拼接 Skill、Memory、CLAUDE.md、工具摘要等内容。
- `subagents/task_subagent.py`
  - 仍只调用 `build_subagent_system_prompt(workdir)` 或新签名。
  - 子 Agent 的 prompt profile 应比主 Agent 更强调：
    - 上下文隔离。
    - 不返回中间对话。
    - 默认只读 Memory。
    - 默认不能创建子 Agent。

当前项目和 s10 的关系：

- 当前 `managers/system_prompt_builder.py` 已经做了最小组装：
  - 核心 prompt。
  - Skill 目录。
  - Memory 索引。
- s10 的目标不是重写 Agent Loop，而是把这套 builder 正式升级成 section 化系统。
- s10 完成后，后续新增能力时只新增 section 或扩展 context，不再直接改 `SYSTEM_WITH_TOOLS` 大字符串。

System Prompt 组装流程：

```text
1. agent_loop / task_subagent 请求 system prompt。
2. 创建 SystemPromptContext。
3. builder 根据 agent_type 选择 section profile。
4. 逐个构建 section。
5. 过滤空 section。
6. 按固定顺序拼接。
7. 使用 cache key 判断是否命中缓存。
8. 返回最终 system prompt 字符串。
9. agent_loop 将其作为第一条 system message 传给模型。
```

建议 section 内容：

```text
identity:
  说明你是中文代码智能体，负责在当前工作区解决任务。

workspace:
  当前工作目录。

tool_rules:
  工具使用原则：需要查看文件就 read_file，需要写文件就 write_file，命令用 bash。

tool_summary:
  从 BASE_TOOLS 生成简短工具目录，不重复完整 schema。

planning_rules:
  复杂任务先 todo，简单任务不强制。

permission_rules:
  危险操作会走权限检查，不要绕过工具权限。

skills_index:
  可用 Skill 摘要，完整说明通过 load_skill 获取。

memory_rules_and_index:
  Memory 使用规则和 MEMORY.md 索引，正文由 BeforeModelCall 按需注入。

project_instructions:
  CLAUDE.md / AGENTS.md 等项目指令。

runtime_context:
  当前日期、agent 类型、可选运行态。

response_style:
  使用中文，简洁准确，不编造工具结果。
```

静态与动态边界：

```text
静态 section:
  identity
  tool_rules
  planning_rules
  response_style

动态 section:
  workspace
  tool_summary
  skills_index
  memory_rules_and_index
  project_instructions
  runtime_context
```

注意：

- 第一版只是字符串级缓存，不等同于 Claude Code 的 API prompt cache。
- 未来如果模型服务支持 prompt cache，可以利用 `STATIC_DYNAMIC_BOUNDARY` 把静态 section 放在更稳定的位置。

验收：

- `agent_loop.py` 不出现大段 system prompt 文本。
- 主 Agent 和子 Agent 都通过 `system_prompt_builder.py` 获取 system prompt。
- builder 输出 section 顺序稳定。
- `BASE_TOOLS` 变化后，工具摘要能自动变化。
- `skills/` 变化后，Skill 目录能自动变化。
- `.memory/private/MEMORY.md` 或 `.memory/team/MEMORY.md` 变化后，Memory 索引能自动变化。
- 存在 `CLAUDE.md` 或 `AGENTS.md` 时，项目指令能被注入。
- 相关 Memory 正文仍然只通过 `BeforeModelCall` 注入 messages，不进入 system prompt。
- 子 Agent prompt 不包含“可以写 Memory”的误导性说明，除非配置允许子 Agent 写 Memory。
- 连续两次 context 不变时，prompt builder 能命中字符串缓存。

## 14. s11: Error Recovery

主题：错误不是结束，是重试的开始。

目标：

- 在不破坏现有 Agent Loop、Hook、Context Compact、System Prompt 结构的前提下，为模型调用增加统一的错误分类、重试和恢复机制。
- 让 Agent 遇到输出截断、上下文超限、临时 API 错误时优先恢复，而不是直接崩溃。
- 将错误恢复逻辑从 `agent_loop.py` 中抽离出来，避免主循环继续膨胀。

设计原则：

- s08 负责“怎么压缩”，s11 负责“什么时候因为错误触发压缩并重试”。
- `RecoveryManager` 只包裹模型调用和模型返回状态，不接管工具权限、Todo、Memory、Skill、System Prompt。
- 临时错误重试时不修改 `state.messages`，避免失败请求污染上下文。
- 上下文超限时复用 `CompactManager.reactive_compact(...)`，不重复写一套压缩逻辑。
- 输出截断只通过续写消息恢复，不把截断处理写进 prompt builder。

要完成什么：

- 把当前 `agent_loop.py` 中的上下文超限判断迁移到 `managers/recovery_manager.py`。
- 新增模型调用恢复入口，统一处理：
  - `finish_reason == "length"`：输出被截断，注入中文续写提示，下一轮继续。
  - context length / prompt too long：调用 s08 的 reactive compact 后重试。
  - 429、500、502、503、504、529、timeout、connection error：指数退避后重试。
- 支持配置最大重试次数、退避参数、可重试状态码、错误关键字和备用模型。
- 记录恢复过程日志，便于测试时判断错误是否被正确分类。
- 重试耗尽后给出清晰错误，不无限循环。

文件设计：

```text
configs/
└── recovery_config.yml
state/
└── recovery_state.py
prompts/
└── recovery_prompts.py
managers/
└── recovery_manager.py
agent_loop.py
utils/
└── config_handler.py
```

文件职责：

- `configs/recovery_config.yml`
  - `ENABLE_RECOVERY`：是否启用错误恢复。
  - `MAX_TRANSIENT_RETRIES`：临时 API 错误最大重试次数。
  - `MAX_CONTEXT_RECOVERY_RETRIES`：上下文超限最大 reactive compact 次数。
  - `MAX_CONTINUATION_RETRIES`：输出截断后最大续写次数。
  - `BACKOFF_BASE_SECONDS`：指数退避起始时间。
  - `BACKOFF_MAX_SECONDS`：指数退避最大等待时间。
  - `BACKOFF_JITTER_RATIO`：抖动比例，避免并发请求同时重试。
  - `RETRY_STATUS_CODES`：可重试 HTTP 状态码，例如 `429/500/502/503/504/529`。
  - `CONTEXT_ERROR_KEYWORDS`：上下文超限关键字，例如 `context length`、`prompt too long`、`too many tokens`。
  - `TRANSIENT_ERROR_KEYWORDS`：临时错误关键字，例如 `timeout`、`connection reset`、`overloaded`。
  - `FALLBACK_MODEL_ID`：可选备用模型，连续过载时切换。

- `state/recovery_state.py`
  - 定义 `RecoveryState`，记录：
    - 当前临时错误重试次数。
    - 当前上下文恢复次数。
    - 当前续写次数。
    - 是否已经切换备用模型。
    - 最近一次错误类型和错误原因。
  - 定义 `RecoveryDecision`，描述一次错误分类后的动作：
    - `retry`：原请求重试。
    - `compact_retry`：先压缩再重试。
    - `continue_generation`：注入续写提示后进入下一轮。
    - `raise`：重试耗尽，向外抛出。

- `prompts/recovery_prompts.py`
  - 存放中文续写提示，不硬编码在主循环中。
  - 建议内容：

```python
CONTINUATION_PROMPT = (
    "上一条回答因为输出长度限制被截断。"
    "请从中断处继续，不要道歉，不要重复已经说过的内容，"
    "也不要重新总结任务背景。"
)
```

- `managers/recovery_manager.py`
  - `create_chat_completion(...)`
    - 包裹 `client.chat.completions.create(...)`。
    - 内部处理临时 API 错误退避重试。
    - 捕获上下文超限错误后调用 `CompactManager.reactive_compact(...)`。
    - 成功后返回模型 response。
  - `classify_error(exc)`
    - 根据状态码、异常类型、错误文本分类为：
      - `context_length`
      - `rate_limit`
      - `server_overloaded`
      - `network_timeout`
      - `unknown`
  - `is_context_length_error(exc)`
    - 从当前 `agent_loop.py` 迁移出来，统一维护上下文超限关键字。
  - `is_transient_error(exc)`
    - 判断 429、5xx、529、超时、连接异常是否可重试。
  - `backoff_delay(attempt, retry_after=None)`
    - 使用 `min(base * 2^attempt, max)` 加随机抖动。
    - 如果服务端返回 `Retry-After`，优先使用服务端建议。
  - `handle_length_finish(state, assistant_message)`
    - 当 `finish_reason == "length"` 时判断是否还允许续写。
    - 允许时返回一条中文续写 user message。
    - 超过次数时返回停止原因。

- `utils/config_handler.py`
  - 增加 `load_recovery_config()`。
  - 复用现有 YAML 读取方式，保持配置加载入口统一。

- `agent_loop.py`
  - 保留主循环顺序：
    1. `BeforeModelCall` hooks。
    2. `normalize_messages(...)`。
    3. 调用 `RECOVERY_MANAGER.create_chat_completion(...)`。
    4. 追加 assistant message。
    5. `AfterModelCall` hooks。
    6. 如果 `finish_reason == "length"`，追加续写提示并 `continue`。
    7. 如果有工具调用，进入工具分发。
    8. 如果没有工具调用，结束循环。
  - 删除主循环里零散的错误关键字判断，把恢复判断交给 `RecoveryManager`。

模型调用阶段的恢复顺序：

1. `BeforeModelCall` 先执行已有 Hook。
   - Todo reminder、Memory 相关内容、Context Compact 仍然在这一阶段完成。
   - 这里属于正常调用前整理，不属于错误恢复。

2. `agent_loop.py` 调用 `RecoveryManager.create_chat_completion(...)`。
   - `RecoveryManager` 内部实际调用 OpenAI Chat Completions。
   - 临时错误不会写入 `state.messages`。

3. 如果模型调用成功：
   - 返回 response。
   - 主循环继续处理 `finish_reason`、工具调用和最终回答。

4. 如果发生临时 API 错误：
   - 触发条件：429、500、502、503、504、529、timeout、connection error。
   - 恢复方法：指数退避 + 抖动后重试同一个请求。
   - 所属级别：调用级恢复。
   - 执行结果：
     - 未超过 `MAX_TRANSIENT_RETRIES` 时继续重试。
     - 连续过载且配置了 `FALLBACK_MODEL_ID` 时可切换备用模型。
     - 超过次数后抛出清晰错误。

5. 如果发生上下文超限错误：
   - 触发条件：异常文本或错误码命中 `CONTEXT_ERROR_KEYWORDS`。
   - 恢复方法：调用 `CompactManager.reactive_compact(messages, client, model_id)`。
   - 所属级别：L5，应急压缩恢复。
   - 执行结果：
     - 压缩成功后重试模型调用。
     - 超过 `MAX_CONTEXT_RECOVERY_RETRIES` 后抛出错误。
     - 不在 `RecoveryManager` 中重新实现 compact，只复用 s08。

6. 如果模型返回 `finish_reason == "length"`：
   - 触发条件：模型成功返回，但输出被 `max_tokens` 截断。
   - 恢复方法：追加中文续写提示，下一轮继续生成。
   - 所属级别：输出级恢复。
   - 执行结果：
     - 已返回的 assistant 内容保留到 `state.messages`。
     - 再追加一条 user 续写消息。
     - 未超过 `MAX_CONTINUATION_RETRIES` 时进入下一轮。
     - 超过次数后停止续写，返回已获得内容或抛出明确错误。

7. 如果工具执行失败：
   - 触发条件：工具 handler 抛异常、参数解析失败、权限拒绝。
   - 恢复方法：继续沿用 dispatcher 当前做法，把错误作为 tool result 返回给模型。
   - 所属级别：模型自纠恢复。
   - 执行结果：
     - 不由 `RecoveryManager` 自动重试工具。
     - 下一轮模型根据工具错误决定是否修正参数或换方法。

与现有模块的关系：

- 与 s08 Context Compact：
  - `RecoveryManager` 只负责判断“是否因为错误触发 reactive compact”。
  - `CompactManager` 继续负责 transcript 写入、摘要生成和消息替换。

- 与 s10 System Prompt：
  - System Prompt 仍然在循环开始前由 `SystemPromptBuilder` 构建。
  - s11 不修改提示词组装顺序，只处理调用失败后的恢复。

- 与 Hooks：
  - s11 初版不强制新增 Hook 事件。
  - 模型调用错误属于调用控制流，放在 `RecoveryManager` 更清晰。
  - 如果后续需要观测，可再新增 `ModelError` / `RecoveryAttempt` hook，但不是本阶段必要项。

- 与子 Agent：
  - 子 Agent 也可以复用 `RecoveryManager.create_chat_completion(...)`。
  - 子 Agent 使用自己的 messages 和 tools，但错误分类、退避、上下文恢复策略保持一致。
  - 子 Agent 的 reactive compact 只压缩子 Agent 自己的上下文，不修改主 Agent 历史。

验收：

- 模拟 502 / 503 / 529，日志中能看到指数退避和重试次数，成功后主循环继续。
- 模拟 429，能按配置重试，超过次数后输出清晰错误。
- 模拟 context length / prompt too long，能调用 `CompactManager.reactive_compact(...)` 后重试。
- 模拟 `finish_reason == "length"`，能追加中文续写提示并继续生成。
- 重试失败不会把失败请求写入 `state.messages`。
- 工具参数错误和权限拒绝仍然作为 tool result 交给模型自纠，不被错误恢复层吞掉。
- 主 Agent 和子 Agent 都能复用同一套错误恢复策略。

## 15. s12: Task System

主题：目标太大，拆成小任务、排好序、持久化。

定位：

- Task System 是 Harness 层能力：把用户的大目标拆成可恢复、可认领、可追踪的持久任务图。
- 它不是 s05 `todo` 的替代品。`todo` 是当前会话内的短期执行清单；`task` 是跨会话、跨 Agent 的工作看板。
- 它也不直接执行代码。执行仍由主 Agent、子 Agent、后台任务或后续 teammate 完成；Task System 只负责“有什么工作、谁在做、做到了哪一步、哪些任务被依赖阻塞”。

核心句：

> 大目标拆成小任务，任务之间按依赖排序，每个任务落盘保存。Agent 重启后能从 `.tasks/` 恢复进度；多 Agent 场景下能基于 `owner` 认领任务，避免重复工作。

目标：

- 建立 `.tasks/` 文件持久化任务图。
- 支持大目标拆分成多个任务，并用 `blockedBy` / `blocks` 表达依赖关系。
- 支持任务排序、可开始判断、认领、状态推进和完成后解锁下游。
- 为 s13 Background Tasks、s15 Agent Teams、s17 Autonomous Agents、s18 Worktree Isolation 提供共享任务基础。
- 明确区分三层概念：
  - `todo`：当前 Agent 当前会话的短期计划，保存在内存里。
  - `task` 子 Agent 工具：同步启动一个临时子 Agent，完成一次委托。
  - `Task System`：持久任务图，保存在 `.tasks/`，可跨会话恢复。

要完成什么：

- 新增持久任务模型 `TaskRecord`。
- 新增任务管理器 `TaskManager`，统一处理读写、校验、排序、认领和完成。
- 新增任务工具，让模型可以创建任务、查看任务、更新任务、认领任务、完成任务。
- 新增任务系统提示词规则，要求模型在大目标、跨会话、可并行或多 Agent 协作场景下优先创建持久任务。
- 新增 `.tasks/` 目录结构，任务文件一任务一 JSON，事件追加写入 JSONL。
- 主循环启动时不自动执行任务，只把任务工具暴露给模型；后续 s17 才做自动扫描和自主认领。

与 TodoWrite 的边界：

| 能力 | s05 `todo` | s12 Task System |
|---|---|---|
| 作用 | 当前会话执行计划 | 持久任务图 |
| 存储 | 进程内 `PlanningState` | `.tasks/` 文件 |
| 生命周期 | 当前任务结束即可丢弃 | 跨会话保留 |
| 依赖关系 | 无 | `blockedBy` / `blocks` |
| 分工 | 不记录 owner | 支持 owner / claim |
| 多 Agent | 不适合作共享看板 | 是后续团队协作基础 |
| 粒度 | Agent 自己的步骤 | 可被认领、恢复、解锁的任务 |

什么时候用 `todo`：

- 当前用户请求在一次会话内即可完成。
- 需要列执行步骤、更新当前进度。
- 不需要跨会话恢复，也不需要其他 Agent 认领。

什么时候用 Task System：

- 用户目标明显很大，需要拆成多个可独立推进的工作项。
- 工作存在先后顺序，例如“先建 schema，再写 API，再写测试”。
- 用户要求持久化进度、恢复进度、多人/多 Agent 协作。
- 后续任务可能交给后台、队友或独立 worktree 执行。

文件设计：

```text
configs/
└── task_config.yml
state/
└── task_state.py
prompts/
└── task_prompts.py
tools_configs/
└── base_configs.py                 # 直接追加 TASK_TOOLS 并合并进 BASE_TOOLS
handlers/
└── base_handlers.py                 # 直接实现并注册 handle_task_* handlers
managers/
└── task_manager.py
.tasks/
├── index.json                       # 看板摘要和高水位 ID
├── events.jsonl                     # create / update / claim / complete 事件
├── locks/
│   └── <task_id>.lock               # 轻量文件锁，避免多 Agent 并发认领覆盖
└── tasks/
    └── <task_id>.json
```

任务数据模型：

`state/task_state.py`

```python
from dataclasses import dataclass, field
from typing import Dict, List, Optional

TASK_STATUSES = {"pending", "in_progress", "completed", "cancelled"}

@dataclass
class TaskRecord:
    id: str
    subject: str
    description: str = ""
    status: str = "pending"
    owner: Optional[str] = None
    active_form: str = ""
    blocked_by: List[str] = field(default_factory=list)
    blocks: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
```

字段说明：

| 字段 | 说明 |
|---|---|
| `id` | 稳定任务 ID，建议 `task_000001` 递增，避免时间戳排序不稳定 |
| `subject` | 一行短标题，列表视图主要展示它 |
| `description` | 完整任务说明，跨会话恢复时必须读它 |
| `status` | `pending` / `in_progress` / `completed` / `cancelled` |
| `owner` | 当前认领者，例如 `main`、`subagent:alice`，为空表示未认领 |
| `active_form` | 进行时短语，用于列表展示当前正在做什么 |
| `blocked_by` | 上游依赖；这些任务未完成前不能开始 |
| `blocks` | 下游任务；便于完成后快速提示被解锁任务 |
| `metadata` | 预留给 s13/s18，例如 background task id、worktree path |
| `created_at` / `updated_at` | ISO 时间戳，用于恢复和审计 |

持久化格式：

`.tasks/tasks/task_000001.json`

```json
{
  "id": "task_000001",
  "subject": "设计数据库 schema",
  "description": "根据现有数据模型设计最小可用 schema，并说明迁移步骤。",
  "status": "pending",
  "owner": null,
  "active_form": "",
  "blocked_by": [],
  "blocks": ["task_000002", "task_000004"],
  "metadata": {},
  "created_at": "2026-07-07T21:00:00+08:00",
  "updated_at": "2026-07-07T21:00:00+08:00"
}
```

`.tasks/index.json`

```json
{
  "version": 1,
  "next_id": 5,
  "tasks_dir": "tasks",
  "updated_at": "2026-07-07T21:00:00+08:00"
}
```

`.tasks/events.jsonl`

```jsonl
{"time":"2026-07-07T21:00:00+08:00","event":"create","task_id":"task_000001","owner":null}
{"time":"2026-07-07T21:05:00+08:00","event":"claim","task_id":"task_000001","owner":"main"}
{"time":"2026-07-07T21:20:00+08:00","event":"complete","task_id":"task_000001","owner":"main","unblocked":["task_000002","task_000004"]}
```

任务依赖规则：

- `blocked_by` 是权威上游依赖。任务能否开始由它决定。
- `blocks` 是反向索引，用于列表展示和完成后提示下游解锁；创建或更新依赖时由 `TaskManager` 自动维护。
- 缺失的依赖任务视为阻塞，不允许认领。
- `cancelled` 任务默认不算完成；如果后续需要“取消后解锁”，应显式提供 `resolve_cancelled_dependencies` 配置，本阶段不做。
- 本阶段实现最小 DAG 保护：新增依赖时检查是否会形成环；如果检查复杂，至少在文档和工具输出中把“环检测失败则拒绝更新”作为验收要求。

任务排序规则：

- `task_list` 默认按可执行优先级输出：
  1. `in_progress` 且有 owner 的任务。
  2. `pending` 且 `can_start == true` 的任务。
  3. `pending` 但被依赖阻塞的任务。
  4. `completed`。
  5. `cancelled`。
- 同一组内按 `id` 升序，保证输出稳定。
- `task_list` 每条任务需要展示 `ready` / `blocked`、owner、status、blocked_by 数量，避免模型误认领。

状态机：

```text
pending ── claim ──> in_progress ── complete ──> completed
   │                     │
   └── cancel ───────────┴──────────────> cancelled
```

约束：

- `claim` 只允许 `pending -> in_progress`。
- `claim` 前必须 `can_start(task_id) == True`。
- `complete` 只允许完成 `in_progress` 任务；默认要求 owner 一致。
- `update` 可以修改 subject、description、active_form、metadata 和依赖，但修改依赖必须保持无环。
- 本阶段暂不提供自动 release。后续 s15/s16 shutdown 时再设计“owner 退出后 unassign 未完成任务”。

管理器设计：

- `managers/task_manager.py`
  - `ensure_store()`：创建 `.tasks/`、`.tasks/tasks/`、`.tasks/locks/` 和 index。
  - `create(subject, description="", blocked_by=None, metadata=None)`：创建任务并落盘。
  - `get(task_id)`：读取完整任务。
  - `list_all(include_completed=True)`：读取全部任务并按默认规则排序。
  - `can_start(task_id)`：检查上游依赖是否全部 completed。
  - `claim(task_id, owner)`：在锁内重新读取、检查依赖、设置 owner 和 `in_progress`。
  - `complete(task_id, owner=None, summary="")`：标记完成，返回刚刚解锁的下游任务。
  - `update(task_id, **changes)`：更新字段和依赖关系，维护 `blocks` 反向索引。
  - `cancel(task_id, reason="")`：标记取消，不删除文件。
  - `append_event(event, task_id, payload=None)`：追加审计事件。
  - `detect_cycle(task_id, new_blocked_by)`：依赖更新时做环检测。

文件写入要求：

- JSON 写入使用临时文件 + replace，避免进程中断留下半个 JSON。
- `claim` 和 `complete` 需要文件锁保护，锁内必须重新读取任务，防止 TOCTOU。
- 任务文件损坏时不要让整个 Agent 崩溃；`task_list` 应返回清晰错误，提示哪个文件不可解析。
- 不把 `.tasks/` 写入长期 Memory。Task 是运行状态，不是用户偏好或项目知识。

工具设计：

- 不新增 `tools_configs/task_configs.py`。
- 在 `tools_configs/base_configs.py` 中直接定义 `TASK_TOOLS`，再追加到 `BASE_TOOLS`。
  - `task_create`
  - `task_list`
  - `task_get`
  - `task_update`
  - `task_claim`
  - `task_complete`
  - `task_cancel`
- 不新增 `handlers/task_handlers.py`。
- 在 `handlers/base_handlers.py` 中直接实现 `handle_task_create`、`handle_task_list`、`handle_task_get`、`handle_task_update`、`handle_task_claim`、`handle_task_complete`、`handle_task_cancel`，并注册到 `BASE_HANDLERS`。
- `base_handlers.py` 顶部导入 `TASK_MANAGER` 或在文件内创建单例，所有 task handler 只做参数取值和调用 manager，不写持久化细节。

建议工具 schema：

`task_create`

```json
{
  "subject": "短标题，必填",
  "description": "完整任务说明，可选",
  "blocked_by": ["task_000001"],
  "metadata": {}
}
```

`task_list`

```json
{
  "include_completed": true,
  "owner": "可选，只看某个 owner",
  "status": "可选，pending/in_progress/completed/cancelled"
}
```

`task_get`

```json
{"task_id": "task_000001"}
```

`task_update`

```json
{
  "task_id": "task_000001",
  "subject": "可选",
  "description": "可选",
  "active_form": "可选",
  "blocked_by": ["可选，传入完整替换后的依赖列表"],
  "metadata": {}
}
```

`task_claim`

```json
{
  "task_id": "task_000001",
  "owner": "main"
}
```

`task_complete`

```json
{
  "task_id": "task_000001",
  "owner": "main",
  "summary": "可选，完成摘要"
}
```

`task_cancel`

```json
{
  "task_id": "task_000001",
  "reason": "取消原因"
}
```

工具输出要求：

- `task_create` 返回新任务 ID、标题、是否被依赖阻塞。
- `task_list` 返回稳定、短小的表格或列表，不返回完整 description。
- `task_get` 返回完整 JSON，供恢复上下文。
- `task_claim` 失败时必须说明原因：已被认领、已完成、依赖未完成、任务不存在、锁获取失败。
- `task_complete` 返回完成确认和刚刚解锁的任务列表。
- 所有工具错误都作为普通 tool result 返回给模型自纠，不交给 s11 recovery 重试。

Prompt 规则：

`prompts/task_prompts.py` 提供 `TASK_SYSTEM_RULES`，并在 `prompt_sections.py` / `system_prompt_builder.py` 中接入。

建议内容：

```text
持久任务规则：
- 大目标、跨会话目标、可并行目标或用户明确要求“拆任务/持久化/多人协作”时，优先使用 task_create 建立持久任务图。
- task 是跨会话工作看板；todo 是当前会话执行计划。不要把 todo 当作持久任务，也不要为简单一次性请求创建 task。
- 认领任务前先确认依赖已完成。被 blocked_by 阻塞的任务不能开始。
- 开始执行某个持久任务前调用 task_claim；完成后调用 task_complete。
- task_get 用于恢复完整任务说明；task_list 只用于看板摘要。
```

与现有模块的接入点：

- `tools_configs/base_configs.py`：直接定义 `TASK_TOOLS` 并合并到 `BASE_TOOLS`，保持所有主 Agent 工具 schema 的统一出口。
- `handlers/base_handlers.py`：直接实现 `handle_task_*`，并注册到 `BASE_HANDLERS`，保持 dispatcher 只依赖一个 handler 注册表。
- `managers/system_prompt_builder.py`：新增任务规则 section，主 Agent 默认注入；子 Agent 是否注入由配置控制。
- `state/agent_state.py`：当前不必把任务状态塞进 `LoopState`。任务状态以 `.tasks/` 为准，避免内存状态和磁盘状态分叉。
- `hooks/builtin_hooks.py`：本阶段不强制加 watcher；可以在 `Stop` Hook 中提示“有未完成 in_progress task”，但不要自动完成任务。
- `subagents/task_subagent.py`：本阶段子 Agent 默认不直接认领持久任务，除非父 Agent 明确把 task_id 和 owner 传给它。后续团队章节再开放给 teammate。

配置：

`configs/task_config.yml`

```yaml
ENABLE_TASK_SYSTEM: true
TASK_DIR: ".tasks"
TASK_ID_PREFIX: "task_"
ENABLE_TASK_LOCKS: true
LOCK_TIMEOUT_SECONDS: 5
MAX_TASKS_IN_LIST_OUTPUT: 50
ALLOW_SUBAGENT_TASK_TOOLS: false
REQUIRE_OWNER_TO_COMPLETE: true
ENABLE_CYCLE_DETECTION: true
```

开发顺序：

1. 新增 `TaskRecord` 和 `TaskManager`，先完成文件持久化和 CRUD。
2. 实现 `blocked_by` / `blocks` 双向维护和 `can_start`。
3. 实现 `task_create`、`task_get`、`task_list` 三个只读/轻写工具，确认模型能创建和查看看板。
4. 实现 `task_claim`、`task_complete`，加入状态机校验和依赖解锁提示。
5. 实现 `task_update`、`task_cancel`，补齐依赖编辑、环检测和取消路径。
6. 接入 system prompt 规则，明确 todo 与 task 的使用边界。
7. 用固定 prompt 做端到端测试：创建 DAG、认领可执行任务、完成上游、查看下游解锁。

示例流程：

```text
用户：把这个项目改造成支持登录、权限和审计日志，拆成可恢复任务。

Agent：
1. task_create: 设计用户表和权限表
2. task_create: 实现登录 API，blocked_by=[设计用户表和权限表]
3. task_create: 实现权限中间件，blocked_by=[设计用户表和权限表]
4. task_create: 添加审计日志，blocked_by=[实现登录 API, 实现权限中间件]
5. task_list: 输出看板
6. task_claim: 认领第一个未阻塞任务
7. todo: 为当前认领任务列短期执行计划
8. 执行工具完成当前任务
9. task_complete: 标记完成，查看被解锁任务
```

关键点：持久任务负责“项目级工作图”，`todo` 负责“当前认领任务的局部步骤”。

验收：

- 任务数据持久化到 `.tasks/`。
- 依赖未完成的任务不能被认领。
- todo 和 task 不混用。
- `task_list` 能稳定展示 ready / blocked / in_progress / completed。
- 完成上游任务后，`task_complete` 能返回被解锁的下游任务。
- 修改依赖时不能形成环。
- 同一个 pending 任务不能被两个 owner 同时认领。
- 重启进程后，`task_list` 和 `task_get` 能从 `.tasks/` 恢复同一批任务。
- 工具参数错误、任务不存在、JSON 损坏、依赖缺失都返回清晰错误，不让主循环崩溃。
- 子 Agent 默认看不到持久任务工具；主 Agent 可把某个 task 的完整说明作为普通子任务委托给 s06 `task` 工具。

## 16. s13: Background Tasks

主题：慢操作丢后台，Agent 继续处理。

定位：

- Background Tasks 是 Harness 层能力：把长耗时命令从主循环中拆出去异步执行。
- 它不替代 s12 Task System。Task System 管“目标和进度”，Background Tasks 管“某个耗时动作怎么跑”。
- 当前阶段只设计本地后台命令，优先支持 `bash` 工具的后台执行；后续再扩展到后台子 Agent、远程 Agent、workflow、监控任务。

核心句：

> 慢操作丢后台，后台线程跑命令，主 Agent 先拿到 `bg_id` 继续处理其他工作；后台完成后通过 Hook 把 `<task_notification>` 注入到后续模型上下文。

目标：

- 支持长时间命令后台执行。
- 主循环不等待慢命令结束。
- 后台任务完成后，在后续轮次自动注入完成通知。
- 支持查看后台任务状态和读取输出摘要。
- 后台输出落盘，避免大 stdout/stderr 直接塞进上下文。

要完成什么：

- 在 `bash` 工具 schema 中增加 `run_in_background` 可选参数。
- 新增 `BackgroundManager`，负责启动后台线程、记录状态、写日志、收集通知。
- 在 `base_handlers.py` 的 `handle_bash` 中判断是否后台执行。
- 在 `BeforeModelCall` Hook 中 drain 后台完成通知，并追加到 `state.messages`。
- 增加轻量状态查询工具，便于模型主动检查后台任务。
- 将后台运行状态保存到 `.runtime-tasks/`。

同步执行和后台执行的区别：

| 能力 | s12 同步工具 | s13 后台任务 |
|---|---|---|
| 慢命令 | Agent 等工具返回 | 后台线程执行 |
| tool result | 命令完整结果 | 立即返回 `bg_id` 占位结果 |
| 完成结果 | 当前轮可见 | 后续轮次注入通知 |
| 输出保存 | 直接进上下文，可能很大 | stdout/stderr 写入文件 |
| 典型命令 | `pwd`、`git status`、`ls` | `npm install`、`pytest`、`docker build` |

边界：

- 本阶段后台任务只在当前 Agent 进程内执行。进程退出时 daemon 线程会终止，已经启动的 Python 线程不会跨进程恢复。
- `.runtime-tasks/` 保存状态和输出，主要用于审计、查看和避免输出丢失；不是完整的系统级任务调度器。
- 如果需要“进程退出后命令仍继续跑”，后续应改为独立 subprocess + PID 管理，不在 s13 最小实现中完成。

文件设计：

```text
configs/
└── background_config.yml
state/
└── background_state.py
managers/
└── background_manager.py
prompts/
└── background_prompts.py
tools_configs/
└── base_configs.py                 # 给 bash 增加 run_in_background，并追加后台查询工具
handlers/
└── base_handlers.py                # handle_bash 接入后台执行，直接实现后台查询 handler
hooks/
├── builtin_hooks.py                # BeforeModelCall 注入后台完成通知
└── hook_manager.py                 # 注册 background hook
.runtime-tasks/
├── index.json
├── events.jsonl
└── outputs/
    └── <bg_id>.txt
```

不新增 `background_configs.py` 或 `background_handlers.py`。当前项目已经把工具定义和 handler 集中在 `base_configs.py` / `base_handlers.py`，s13 继续沿用这个模式。

状态模型：

`state/background_state.py`

```python
from dataclasses import dataclass, field
from typing import Dict, Optional

BACKGROUND_STATUSES = {"running", "completed", "failed", "cancelled"}

@dataclass
class BackgroundTaskRecord:
    id: str
    command: str
    status: str = "running"
    exit_code: Optional[int] = None
    output_path: str = ""
    owner: str = "main"
    started_at: str = ""
    finished_at: str = ""
    summary: str = ""
    metadata: Dict = field(default_factory=dict)
    notified: bool = False
```

持久化格式：

`.runtime-tasks/index.json`

```json
{
  "version": 1,
  "next_id": 2,
  "tasks": {
    "bg_000001": {
      "id": "bg_000001",
      "command": "pytest",
      "status": "running",
      "output_path": ".runtime-tasks/outputs/bg_000001.txt",
      "started_at": "2026-07-07T22:30:00+08:00",
      "notified": false
    }
  }
}
```

`.runtime-tasks/events.jsonl`

```jsonl
{"time":"2026-07-07T22:30:00+08:00","event":"start","bg_id":"bg_000001","command":"pytest"}
{"time":"2026-07-07T22:31:12+08:00","event":"complete","bg_id":"bg_000001","exit_code":0}
{"time":"2026-07-07T22:31:13+08:00","event":"notify","bg_id":"bg_000001"}
```

管理器设计：

- `managers/background_manager.py`
  - `ensure_store()`：创建 `.runtime-tasks/` 和输出目录。
  - `run_command(command, owner="main", cwd=None, timeout=None)`：创建 `bg_id`，启动 daemon 线程，立即返回占位结果。
  - `_worker(bg_id, command, cwd, timeout)`：在线程中执行命令，把 stdout/stderr 写入 `.runtime-tasks/outputs/<bg_id>.txt`。
  - `get(bg_id)`：读取单个后台任务状态。
  - `list_all(include_completed=True)`：列出后台任务。
  - `drain_notifications()`：取出已完成但未通知的任务，生成 `<task_notification>`。
  - `append_event(event, bg_id, payload=None)`：追加事件日志。
  - `summarize_output(output_path)`：生成短摘要，避免把大输出注入上下文。

命令执行策略：

- 后台线程用 `threading.Thread(..., daemon=True)`。
- 命令执行复用当前 `tools.bash_tools.run_bash` 的平台逻辑，或者在 `BackgroundManager` 中统一使用 `subprocess.run(..., cwd=Path.cwd(), capture_output=True, text=True)`。
- 输出文件包含 command、exit code、stdout、stderr，便于后续人工查看。
- 线程内部捕获异常，状态改为 `failed`，异常信息写入输出文件。
- 后台 manager 的内存状态和 `index.json` 都要更新；如果内存丢失，至少能从 `index.json` 查到历史状态。

工具设计：

- `tools_configs/base_configs.py`
  - 给现有 `bash` 工具增加字段：
    - `run_in_background`: boolean，默认 false。
    - `background_owner`: string，可选，默认 `main`。
  - 追加后台查询工具：
    - `background_list`
    - `background_get`
- `handlers/base_handlers.py`
  - `handle_bash(args)`：
    - 如果 `args.get("run_in_background")` 为 true，调用 `BACKGROUND_MANAGER.run_command(...)`。
    - 否则继续调用 `run_bash(args["command"])`，保持现有同步行为。
  - `handle_background_list(args)`：调用 manager 列表。
  - `handle_background_get(args)`：读取单个后台任务状态和输出摘要。
  - 在 `BASE_HANDLERS` 中注册 `background_list`、`background_get`。

建议 `bash` schema：

```json
{
  "command": "pytest",
  "run_in_background": true,
  "background_owner": "main"
}
```

后台启动返回：

```text
后台任务已启动: bg_000001
command: pytest
status: running
output_path: .runtime-tasks/outputs/bg_000001.txt
后续完成后会以 <task_notification> 注入。
```

`background_list` 输入：

```json
{
  "include_completed": true
}
```

`background_get` 输入：

```json
{
  "bg_id": "bg_000001",
  "tail_chars": 2000
}
```

通知注入：

- 不建议把通知逻辑硬编码进 `agent_loop.py`。
- 当前项目已经有 Hook 机制，`agent_loop.py` 每轮模型调用前都会触发 `BeforeModelCall`。
- 因此 s13 应新增 `background_before_model_call_hook(context)`：

```python
def background_before_model_call_hook(context: HookContext):
    if context.messages is None:
        return None
    notifications = BACKGROUND_MANAGER.drain_notifications()
    if not notifications:
        return None
    context.messages.append({
        "role": "user",
        "content": "\n\n".join(notifications),
    })
    return None
```

通知格式：

```xml
<task_notification>
  <task_id>bg_000001</task_id>
  <status>completed</status>
  <command>pytest</command>
  <exit_code>0</exit_code>
  <output_path>.runtime-tasks/outputs/bg_000001.txt</output_path>
  <summary>pytest completed, 24 passed in 18.2s</summary>
</task_notification>
```

**为什么通知不用 tool result：**

- **原始 `bash` 工具调用已经立即返回了“后台任务已启动”的 tool result。**
- **后台完成是一个后续事件，不再对应原来的 tool call。**
- **因此完成消息应作为普通 user message 注入，而不是伪造一个新的 tool result。**

Prompt 规则：

`prompts/background_prompts.py`

```text
后台任务规则：
- 预计耗时较长的命令可以设置 bash.run_in_background=true，例如安装依赖、运行完整测试、构建、部署、docker build。
- 后台任务启动后不要声称已经完成，只能说已启动并记录 bg_id。
- 后台任务完成通知会以 <task_notification> 注入；看到通知后再根据 exit_code 和 summary 判断成功或失败。
- 需要主动查看后台任务时调用 background_list 或 background_get。
- 不要把快速命令放后台，例如 pwd、ls、git status、读取小文件。
```

在 `prompt_sections.py` 中加入 `background_rules`，并由 `system_prompt_builder.py` 根据 `background_config.ENABLE_BACKGROUND_TASKS` 注入。

和 Task System 的关系：

- Task System 的 `metadata` 可以保存 `bg_id`，表示某个持久任务正在由后台命令推进。
- 但 s13 不自动修改 `.tasks/` 中的任务状态。
- 后台命令完成后，模型看到通知，再决定是否调用 `task_complete`。

示例流程：

```text
用户：运行完整测试，测试期间继续检查 README。

模型：
1. 调用 bash:
   {"command": "pytest", "run_in_background": true}
2. 立即得到:
   后台任务已启动: bg_000001
3. 继续调用 read_file 读取 README。
4. 后续 BeforeModelCall hook 注入:
   <task_notification>bg_000001 completed...</task_notification>
5. 模型根据通知总结测试结果。
```

错误处理：

- 后台线程异常不应杀掉 Agent 主循环。
- 命令退出码非 0 时，状态记为 `failed`，通知仍然注入。
- `background_get` 读取不存在的 `bg_id` 时，像其他工具一样返回清晰错误，由 dispatcher 交给模型自纠。
- 如果输出文件过大，通知只放摘要和路径，不直接放完整输出。

配置：

`configs/background_config.yml`

```yaml
ENABLE_BACKGROUND_TASKS: true
RUNTIME_TASK_DIR: ".runtime-tasks"
OUTPUT_DIR: ".runtime-tasks/outputs"
TASK_ID_PREFIX: "bg_"
MAX_NOTIFICATION_OUTPUT_CHARS: 1200
MAX_BACKGROUND_TASKS_IN_LIST: 50
DEFAULT_COMMAND_TIMEOUT_SECONDS: 0
SLOW_COMMAND_KEYWORDS:
  - "npm install"
  - "pip install"
  - "pytest"
  - "npm test"
  - "npm run build"
  - "docker build"
  - "cargo build"
  - "make"
```

是否启用启发式：

- 主路径应是模型显式传 `run_in_background=true`。
- 可以保留 `SLOW_COMMAND_KEYWORDS` 做提醒或兜底，但不建议自动把命令后台化，避免模型以为拿到了同步结果。
- 如果要自动后台化，必须在 tool result 中明确说明“命令已后台启动，尚未完成”。

开发顺序：

1. 新增 `BackgroundTaskRecord` 和 `BackgroundManager`。
2. 先实现 `run_command()`、输出落盘、状态更新和 `background_get`。
3. 给 `bash` schema 增加 `run_in_background`，在 `handle_bash` 中分支。
4. 实现 `drain_notifications()`，生成 `<task_notification>`。
5. 在 `hooks/builtin_hooks.py` 注册 `background_before_model_call_hook`。
6. 增加 `background_list` / `background_get` 工具。
7. 加入 prompt 规则，告诉模型慢命令才放后台。
8. 用固定 prompt 测试：后台跑慢命令，同时执行一个快工具，然后看到完成通知。

验收：

- `bash(command="python -c \"import time; time.sleep(3); print('done')\"", run_in_background=true)` 能立即返回 `bg_id`。
- 后台输出能写入 `.runtime-tasks/outputs/<bg_id>.txt`。
- Agent 在后台命令运行期间能继续执行其他工具。
- 后台任务完成后，下一轮 `BeforeModelCall` 能注入 `<task_notification>`。
- `background_list` 能看到 running / completed / failed 状态。
- `background_get` 能读取指定任务摘要和输出路径。
- 退出码非 0 的后台命令会标记为 failed，并注入失败通知。
- 大输出不会直接塞满上下文，只注入摘要和输出路径。
- Task System 不会被后台 manager 自动改状态；是否完成持久任务由模型看到通知后显式调用 `task_complete`。

## 17. s14: Cron Scheduler

主题：按时间表生产工作，调度与执行解耦。

目标：

- 支持五段式 cron 表达式创建定时任务。
- 支持 durable 定时任务跨 Agent 进程重启保留定义。
- 支持 session-only 定时任务只在当前进程内有效。
- 到点后由调度线程生产工作事件，而不是直接调用模型或工具。
- 队列处理器在 Agent 空闲时自动交付定时工作。
- Agent Loop 只消费已触发的工作，不负责检查时间。
- 复用现有工具、权限、Hook、Prompt Builder、后台任务和错误恢复链路。

重要边界：

- Cron Scheduler 是进程内能力。Agent 进程关闭后不会继续触发任务。
- Durable 只表示任务定义写入磁盘，下次 Agent 启动后可以恢复；不是系统级 crontab。
- Cron Manager 不直接执行 shell 命令，也不直接调用 `BACKGROUND_MANAGER`。它只把 prompt 按时间送进 Agent。
- 定时 prompt 如果需要跑慢命令，仍由 Agent 在执行时选择 `bash(run_in_background=true)`。
- Task System 不会被 Cron Manager 自动改状态；是否调用 `task_complete` 由模型根据执行结果判断。

核心设计：

```text
Scheduler
  独立 daemon 线程，每秒检查 cron 表达式是否到点。
  到点后只生成 FiredCronEvent 并写入 cron_queue。

Queue
  进程内触发队列。
  Scheduler 写入，Queue Processor 消费。

Queue Processor
  独立 daemon 线程。
  发现队列非空且 Agent 空闲时，拉起一轮 scheduled agent turn。

Agent Consumer
  从 cron_queue 消费已触发事件。
  把事件格式化为 <scheduled_task> user message。
  调用现有 agent_loop 执行。
```

这四层必须保持解耦：

| 层 | 负责 | 不负责 |
|---|---|---|
| Scheduler | 判断时间、去重、入队 | 调模型、执行工具、修改 messages |
| Queue | 暂存已触发事件 | 判断 cron 是否到点 |
| Queue Processor | 空闲时交付事件 | 解析 cron、决定任务是否触发 |
| Agent Loop | 执行已交付 prompt | 主动扫描定时任务 |

当前代码文件设计：

```text
configs/
└── cron_config.yml
state/
└── cron_state.py
managers/
└── cron_manager.py
prompts/
└── cron_prompts.py
.runtime-tasks/
├── scheduled_tasks.json
├── scheduled_events.jsonl
└── scheduled.lock              # 预留增强项：多进程 durable 去重
```

已接入的现有文件：

```text
agent_loop.py                   # 启动 scheduler；提供 scheduled agent turn 入口；手动/定时共用 agent_lock
tools_configs/base_configs.py   # 追加 schedule_cron/list_crons/cancel_cron schema
handlers/base_handlers.py       # 追加 cron 工具 handler
hooks/builtin_hooks.py          # SessionStart 初始化 cron 存储
hooks/hook_manager.py           # 注册 cron 初始化 hook
managers/system_prompt_builder.py
prompts/prompt_sections.py
utils/config_handler.py
configs/permission_config.yml
```

数据结构：

`state/cron_state.py` 定义任务定义和触发事件。

```python
@dataclass
class CronJobRecord:
    id: str
    cron: str
    prompt: str
    recurring: bool = True
    durable: bool = True
    enabled: bool = True
    created_at: str = ""
    updated_at: str = ""
    last_fired_at: str = ""
    last_fire_marker: str = ""
    fire_count: int = 0
    metadata: Dict = field(default_factory=dict)
```

```python
@dataclass
class FiredCronEvent:
    event_id: str
    job_id: str
    cron: str
    prompt: str
    fired_at: str
    durable: bool
    recurring: bool
```

`CronJobRecord` 是任务定义；`FiredCronEvent` 是到点后进入队列的工作事件。调度器入队的是事件，而不是直接执行任务定义。

配置：

`configs/cron_config.yml`：

```yaml
ENABLE_CRON_SCHEDULER: true
CRON_TASK_DIR: ".runtime-tasks"
CRON_TASK_FILE: ".runtime-tasks/scheduled_tasks.json"
CRON_EVENT_FILE: ".runtime-tasks/scheduled_events.jsonl"
CRON_LOCK_FILE: ".runtime-tasks/scheduled.lock"
CRON_ID_PREFIX: "cron_"
CRON_SESSION_ID_PREFIX: "cron_session_"
CRON_EVENT_ID_PREFIX: "cron_evt_"
CHECK_INTERVAL_SECONDS: 1
QUEUE_PROCESSOR_INTERVAL_SECONDS: 0.2
MAX_CRON_JOBS: 50
MAX_TRIGGERED_EVENTS_PER_TURN: 5
ENABLE_DURABLE_CRON: true
ENABLE_SESSION_CRON: true
```

`utils/config_handler.py` 增加：

- `DEFAULT_CRON_CONFIG`
- `load_cron_config(...)`
- 模块级 `cron_config = load_cron_config()`

`managers/system_prompt_builder.py` 的 prompt cache key 要加入 `cron_config`，避免启用或关闭 cron 后继续复用旧 prompt。

Cron 表达式：

- 使用标准五段式：`分钟 小时 日 月 星期`。
- 支持 `*`、`*/N`、`N`、`N-M`、`N-M/S`、`N,M,...`。
- 不支持秒级 cron、`L`、`W`、`?`。
- 使用本地时区 `datetime.now().astimezone()`。
- day-of-week 使用 cron 语义：Sunday = 0 或 7，Monday = 1。
- day-of-month 和 day-of-week 同时受限时使用 OR 语义。

创建任务前必须调用 `validate_cron(expr)`。加载 durable 文件时也必须校验，坏任务要跳过并写日志，不能拖垮启动。

CronManager：

`managers/cron_manager.py` 提供全局单例：

```python
CRON_MANAGER = CronManager()
```

主要方法：

| 方法 | 作用 |
|---|---|
| `ensure_store()` | 初始化 `.runtime-tasks/`、durable 文件和事件日志 |
| `start(client, model_id, hook_manager, workdir, runner)` | 幂等启动 scheduler 和 queue processor |
| `create(cron, prompt, recurring=True, durable=True)` | 创建定时任务 |
| `cancel(cron_id)` | 取消定时任务 |
| `list_all(include_session=True)` | 列出 durable 和 session-only 定时任务 |
| `validate_cron(expr)` | 校验 cron 表达式 |
| `cron_matches(expr, dt)` | 判断时间是否匹配 |
| `enqueue_due_jobs(now)` | Scheduler 调用，到点任务转事件入队 |
| `has_pending_events()` | Queue Processor 判断是否需要交付 |
| `consume_triggered_events(limit)` | Agent 消费队列事件 |
| `format_events_as_user_message(events)` | 生成 `<scheduled_task>` 注入消息 |

内部状态：

```python
self.lock = threading.RLock()
self.agent_lock = threading.Lock()
self.scheduler_started = False
self.durable_jobs: Dict[str, CronJobRecord] = {}
self.session_jobs: Dict[str, CronJobRecord] = {}
self.queue: Deque[FiredCronEvent] = deque()
self.runner: Optional[AgentRunner] = None
```

`agent_lock` 用来保证手动用户请求和 cron 自动请求不会同时驱动同一个 Agent Loop。

持久化：

Durable 任务写入 `.runtime-tasks/scheduled_tasks.json`：

```json
{
  "version": 1,
  "next_id": 2,
  "tasks": {
    "cron_000001": {
      "id": "cron_000001",
      "cron": "0 9 * * 1-5",
      "prompt": "运行项目测试并总结失败项",
      "recurring": true,
      "durable": true,
      "enabled": true,
      "created_at": "2026-07-08T09:00:00+08:00",
      "updated_at": "2026-07-08T09:00:00+08:00",
      "last_fired_at": "",
      "last_fire_marker": "",
      "fire_count": 0,
      "metadata": {}
    }
  },
  "updated_at": "2026-07-08T09:00:00+08:00"
}
```

Session-only 任务只保存在内存 `self.session_jobs`，不写入磁盘。

触发事件追加到 `.runtime-tasks/scheduled_events.jsonl`。事件日志用于审计，不作为主状态来源：

```jsonl
{"time":"2026-07-08T09:00:00+08:00","event":"fire","event_id":"cron_evt_000001","cron_id":"cron_000001","marker":"2026-07-08 09:00"}
{"time":"2026-07-08T09:00:01+08:00","event":"deliver","event_id":"cron_evt_000001","cron_id":"cron_000001"}
```

Scheduler 线程：

```python
def _scheduler_loop(self):
    while True:
        time.sleep(self.check_interval)
        now = datetime.now().astimezone()
        try:
            self.enqueue_due_jobs(now)
        except Exception:
            logger.exception("cron scheduler tick failed")
```

`enqueue_due_jobs(now)` 的规则：

- 遍历 durable jobs 和 session jobs。
- 每个 job 单独 `try/except`，单个坏任务不影响其他任务。
- `cron_matches(job.cron, now)` 为 true 时才触发。
- 使用 `minute_marker = now.strftime("%Y-%m-%d %H:%M")` 防止同一分钟重复触发。
- 触发后生成 `FiredCronEvent` 并 append 到 `self.queue`。
- 更新 `last_fire_marker`、`last_fired_at`、`fire_count`。
- `recurring=false` 的一次性任务触发后从任务表删除。
- durable 任务状态变化后写回 `scheduled_tasks.json`。

Queue Processor 线程：

```python
def _queue_processor_loop(self):
    while True:
        time.sleep(self.queue_processor_interval)
        if not self.has_pending_events():
            continue
        if not self.agent_lock.acquire(blocking=False):
            continue
        try:
            if self.has_pending_events():
                self._run_scheduled_agent_turn()
        finally:
            self.agent_lock.release()
```

`agent_loop.py` 需要新增一个定时任务执行入口：

```python
def run_scheduled_agent_turn(client, model_id, hook_manager=None) -> str:
    events = CRON_MANAGER.consume_triggered_events(
        limit=cron_config.get("MAX_TRIGGERED_EVENTS_PER_TURN", 5)
    )
    if not events:
        return ""

    message = CRON_MANAGER.format_events_as_user_message(events)
    state = LoopState(messages=[{"role": "user", "content": message}])
    return agent_loop(state, client, model_id, hook_manager=hook_manager)
```

注入格式：

```xml
<scheduled_task>
  <event_id>cron_evt_000001</event_id>
  <cron_id>cron_000001</cron_id>
  <cron>0 9 * * 1-5</cron>
  <fired_at>2026-07-08T09:00:00+08:00</fired_at>
  <prompt>运行项目测试并总结失败项</prompt>
</scheduled_task>
```

为什么不能只靠 `BeforeModelCall` Hook：

- `BeforeModelCall` 只有在已经有一轮 Agent 要调用模型时才执行。
- cron 的目标是无人输入时也能自动交付。
- 所以必须有 queue processor 主动拉起一轮 Agent。
- Hook 可以做初始化或辅助注入，但不能替代无人输入时的启动入口。

启动流程：

`agent_loop.py` 的 `main()` 中，在 `client, model_id = build_model()` 后启动：

```python
CRON_MANAGER.start(
    client=client,
    model_id=model_id,
    hook_manager=hook_manager,
    workdir=str(WORKDIR),
    runner=run_scheduled_agent_turn,
)
```

`start(...)` 必须幂等：

- 未启用 `ENABLE_CRON_SCHEDULER` 时直接返回。
- 已启动时直接返回。
- 先 `ensure_store()`。
- 加载 durable jobs。
- 启动 scheduler daemon 线程。
- 启动 queue processor daemon 线程。
- 保存 `runner` 回调；queue processor 到点交付时通过它进入 `agent_loop`。

手动入口也要使用同一个 `agent_lock`：

```python
with CRON_MANAGER.agent_execution():
    answer = agent_loop(state, client, model_id, hook_manager=hook_manager)
```

这样用户手动请求运行中，cron 不会并发启动另一轮 Agent。

示例流程：

假设用户要求“每 5 分钟检查一次当前目录，并总结是否有新增文件”。

1. 模型创建定时任务：

```json
{
  "cron": "*/5 * * * *",
  "prompt": "检查当前目录文件列表，并总结是否有新增文件。",
  "recurring": true,
  "durable": true
}
```

2. `handle_schedule_cron(...)` 调用 `CRON_MANAGER.create(...)`：

```text
已创建定时任务: cron_000001
cron: */5 * * * *
recurring: True
durable: True
prompt: 检查当前目录文件列表，并总结是否有新增文件。
```

3. durable 任务写入 `.runtime-tasks/scheduled_tasks.json`：

```json
{
  "version": 1,
  "next_id": 2,
  "tasks": {
    "cron_000001": {
      "id": "cron_000001",
      "cron": "*/5 * * * *",
      "prompt": "检查当前目录文件列表，并总结是否有新增文件。",
      "recurring": true,
      "durable": true,
      "last_fire_marker": "",
      "fire_count": 0
    }
  }
}
```

4. 到达匹配分钟时，scheduler 调用 `enqueue_due_jobs(now)`：

```text
cron_matches("*/5 * * * *", now) == True
last_fire_marker != "YYYY-MM-DD HH:MM"
生成 FiredCronEvent
append 到 self.queue
写入 scheduled_events.jsonl 的 fire 事件
```

5. queue processor 发现队列非空，尝试获取 `agent_lock`：

```text
手动 Agent 正在运行 -> 获取锁失败 -> 等下一轮检查
Agent 空闲 -> 获取锁成功 -> 调用 _run_scheduled_agent_turn()
```

6. `runner=run_scheduled_agent_turn` 消费队列并构造 user message：

```xml
<scheduled_task>
  <event_id>cron_evt_000001</event_id>
  <cron_id>cron_000001</cron_id>
  <cron>*/5 * * * *</cron>
  <fired_at>2026-07-08T20:50:00+08:00</fired_at>
  <prompt>检查当前目录文件列表，并总结是否有新增文件。</prompt>
</scheduled_task>
```

7. `agent_loop(...)` 像处理普通用户请求一样处理这条消息。它可以调用 `bash`、`read_file`、`background_list` 等现有工具；如果 prompt 要跑慢命令，仍由模型显式选择 `bash(run_in_background=true)`。

这个流程体现了 s14 的边界：Cron 只负责“什么时候生产工作”和“什么时候交付给空闲 Agent”，真正怎么做仍由 Agent Loop 和工具系统决定。

工具设计：

追加到 `tools_configs/base_configs.py`：

- `schedule_cron`
  - 参数：`cron`、`prompt`、`recurring`、`durable`
  - 创建 durable 或 session-only 定时任务。
- `list_crons`
  - 参数：`include_session`
  - 列出 cron、prompt 摘要、last fired、fire count。
- `cancel_cron`
  - 参数：`cron_id`
  - 删除 durable 或 session-only 定时任务。

追加到 `handlers/base_handlers.py`：

```python
def handle_schedule_cron(args: dict) -> str:
    return CRON_MANAGER.create(
        cron=args["cron"],
        prompt=args["prompt"],
        recurring=args.get("recurring", True),
        durable=args.get("durable", True),
    )

def handle_list_crons(args: dict) -> str:
    return CRON_MANAGER.list_all(
        include_session=args.get("include_session", True),
    )

def handle_cancel_cron(args: dict) -> str:
    return CRON_MANAGER.cancel(args["cron_id"])
```

并追加到 `BASE_HANDLERS`：

```python
"schedule_cron": handle_schedule_cron,
"list_crons": handle_list_crons,
"cancel_cron": handle_cancel_cron,
```

权限设计：

`configs/permission_config.yml` 和 `DEFAULT_PERMISSION_CONFIG` 的 allow 列表追加：

```yaml
- schedule_cron
- list_crons
- cancel_cron
```

创建 cron 任务虽然不立即执行工具，但会让未来自动发起 Agent 请求，所以必须经过现有权限系统。

Prompt 设计：

新增 `prompts/cron_prompts.py`：

```python
CRON_SYSTEM_RULES = """定时任务规则：
- 用户要求“每天/每周/每隔一段时间/定时/提醒/自动检查”时，可以使用 schedule_cron。
- schedule_cron 只创建计划，不表示任务已经执行。
- cron 表达式使用五段式：分钟 小时 日 月 星期。
- 创建任务后要告诉用户 cron_id、cron 表达式、是否 durable、是否 recurring。
- 需要查看或取消定时任务时使用 list_crons 或 cancel_cron。
- 收到 <scheduled_task> 后，把其中 prompt 当作用户在该时间点发来的请求处理。
- 不要声称 Agent 进程关闭后仍能触发 cron；durable 只保留任务定义。
"""
```

`prompts/prompt_sections.py`：

- `MAIN_SECTION_ORDER` 在 `"background_rules"` 后增加 `"cron_rules"`。
- `STATIC_SECTIONS` 增加 `"cron_rules"`。

`managers/system_prompt_builder.py`：

- import `CRON_SYSTEM_RULES`
- import `cron_config`
- 增加 `_cron_rules_prompt(agent_type)`
- `_section_builders(...)` 增加 `"cron_rules"`
- `_cache_key(...)` 增加 `cron_config`

子 Agent 默认不注入 cron 规则，也不暴露 cron 工具。定时调度是主 Agent / Harness 层能力。

多进程边界：

初版先保证单进程可靠。如果同一项目启动多个 Agent 进程，它们都可能加载 durable jobs。要避免重复触发，需要增强 `.runtime-tasks/scheduled.lock` 文件锁：谁拿到锁，谁触发 durable jobs；session-only jobs 仍由各自进程触发。这个可以作为 s14 后续增强，不阻塞初版。

测试和验收：

- `schedule_cron` 能创建 durable 和 session-only 任务。
- `list_crons` 能列出任务 ID、cron、recurring/durable、last fired、fire count。
- `cancel_cron` 能取消任务。
- cron 表达式非法时拒绝创建。
- durable 任务写入 `.runtime-tasks/scheduled_tasks.json`。
- session-only 任务不写入 durable 文件。
- 到点后 Scheduler 只入队，不直接调用模型。
- Queue Processor 在 Agent 空闲时自动交付。
- Agent 收到 `<scheduled_task>` 后像普通用户请求一样执行。
- 同一分钟内同一任务不会重复触发。
- 第二天同一分钟可以再次触发。
- 一次性任务触发后自动删除。
- 单个坏 job 不会杀掉 scheduler 线程。
- 手动 Agent 执行中，cron 不会并发启动另一轮 Agent。
- Agent 进程关闭后不触发任务，这一点在文档和 prompt 中明确说明。

## 18. s15: Agent Teams

主题：一个搞不定，组队来。通过“文件收件箱 + 队友线程”把单 Agent 扩展成 Lead + N 个 teammate 的协作形态。

Harness 层定位：团队。它不替代模型推理和工具执行，而是在 Agent 外侧增加成员注册、消息总线、队友生命周期和 Lead 收件箱注入，让多个 Agent 可以解耦协作。

### 设计目标

- Lead 可以通过工具创建 teammate，并把任务交给 teammate。
- teammate 在独立线程中运行，有自己的 system prompt、messages 和简化工具集。
- Lead 与 teammate 通过文件 inbox 异步通信，发送消息与执行任务解耦。
- Lead 每轮调用模型前自动读取团队 inbox，把队友消息注入上下文。
- 初版只做单进程内多线程团队；跨进程锁、权限冒泡、优雅关闭协议留给 s16。

### 与当前项目结构的关系

建议新增和修改的文件如下：

```text
configs/
└── team_config.yml                 # 团队功能开关、目录、轮询和数量限制
state/
└── team_state.py                   # TeamMessage、TeamMemberRecord 等状态结构
tools/
└── message_bus.py                  # 文件收件箱消息总线
managers/
└── team_manager.py                 # teammate 生命周期与团队工具后端
subagents/
└── teammate_agent.py               # 队友线程中的 Agent 循环
prompts/
└── team_prompts.py                 # Lead/teammate 团队规则 prompt
tools_configs/base_configs.py       # 追加团队工具 schema
handlers/base_handlers.py           # 追加团队工具 handler
hooks/builtin_hooks.py              # 追加 Lead inbox 注入 hook
hooks/hook_manager.py               # 注册团队 hook
managers/system_prompt_builder.py   # 挂载团队规则 prompt section
configs/permission_config.yml       # 默认允许或显式配置团队工具
.team/
├── members.json                    # 团队成员注册表
├── events.jsonl                    # 团队事件流水，便于排查
├── inbox/
│   ├── lead.jsonl
│   ├── alice.jsonl
│   └── bob.jsonl
└── locks/                          # 初版可先用线程锁；后续升级文件锁
```

### 配置设计

`configs/team_config.yml` 负责控制团队功能，不把常量散落在 manager 里：

```yaml
ENABLE_AGENT_TEAMS: true
TEAM_DIR: ".team"
TEAM_INBOX_DIR: ".team/inbox"
TEAM_ID: "default"
LEAD_AGENT_NAME: "lead"
MAX_TEAMMATES: 5
MAX_TEAMMATE_TURNS: 10
TEAM_INBOX_POLL_SECONDS: 1
MAX_INBOX_MESSAGES_PER_TURN: 20
TEAMMATE_RESULT_MAX_CHARS: 6000
```

### 状态结构

`state/team_state.py` 定义可序列化的数据结构，所有落盘内容都使用这些结构转换，避免不同模块拼接不同格式的 dict。

```python
@dataclass
class TeamMemberRecord:
    name: str
    role: str
    prompt: str
    status: str              # starting/running/idle/stopped/failed
    thread_name: str | None
    created_at: str
    updated_at: str
    last_seen_at: str | None
    turn_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TeamMessage:
    id: str
    sender: str
    recipient: str
    type: str                # message/result/error/task_assignment
    content: str
    created_at: str
    correlation_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

### MessageBus：文件收件箱

`tools/message_bus.py` 是团队协作的最小消息总线。每个 Agent 对应一个 `.jsonl` inbox，发送消息就是向收件人的文件追加一行 JSON，读取消息就是读取并消费该文件。

核心 API：

- `ensure_store()`：创建 `.team/`、`inbox/`、`members.json`、`events.jsonl`。
- `send(sender, recipient, content, msg_type="message", metadata=None)`：向单个收件人写入 `TeamMessage`。
- `broadcast(sender, recipients, content, msg_type="message")`：给多个 teammate 发送相同消息。
- `read_inbox(name, consume=True, limit=None)`：读取某个成员的 inbox；`consume=True` 时读完清空。
- `append_event(event_type, payload)`：写入 `events.jsonl`，用于调试 teammate 创建、退出、异常和消息投递。

初版可以在 `MessageBus` 内部为每个 inbox 使用 `threading.Lock`，满足当前单进程多线程场景。真实多进程或多个终端同时写入时，需要在 s16/s18 升级为文件锁，否则 `read + truncate` 和并发 append 可能丢消息。

### TeamManager：团队后端

`managers/team_manager.py` 作为工具 handler 和 teammate 线程之间的门面，负责成员注册、线程启动、消息投递和 Lead inbox 读取。

核心 API：

- `start(client, model_id, hook_manager, workdir)`：初始化团队目录和运行依赖。
- `spawn(name, role, prompt)`：校验数量和名称，写入 `members.json`，启动 teammate daemon 线程。
- `list_all()`：返回当前成员、状态、轮次和最后活跃时间。
- `send_message(to, content, msg_type="message")`：Lead 向某个 teammate 发送消息。
- `broadcast(content, recipients=None)`：Lead 向所有或指定 teammate 广播。
- `check_inbox(agent="lead")`：读取 Lead 或当前 teammate 的 inbox。
- `record_member_status(name, status, error=None)`：线程状态变更时更新注册表。

这里的关键边界是：TeamManager 只调度 teammate 和收发消息，不直接替 teammate 执行 bash/edit_file 等工具。teammate 的实际工作发生在自己的 Agent 循环里。

### teammate 线程

`subagents/teammate_agent.py` 负责 teammate 自己的执行循环。每个 teammate 拥有独立 messages，不共享 Lead 的完整上下文，只通过任务 prompt 和 inbox 获取信息。

运行流程：

1. `TeamManager.spawn()` 创建 `TeamMemberRecord`。
2. 启动 daemon thread，入口为 `run_teammate_agent(...)`。
3. teammate 构造自己的 system prompt，例如“你是 alice，角色是 backend developer，只处理分配给你的任务，通过 `team_send_message` 向 Lead 汇报”。
4. teammate 每轮先读自己的 inbox，把消息追加为 `<team_inbox>...</team_inbox>`。
5. teammate 调用模型，执行允许的简化工具。
6. 达到 `MAX_TEAMMATE_TURNS`、任务完成或异常时，向 `lead` 发送 `result` 或 `error` 消息。

初版 teammate 工具集建议控制在：

- `bash`
- `read_file`
- `write_file`
- `edit_file`
- `team_send_message`
- `team_check_inbox`

teammate 不允许调用 `spawn_teammate`，避免队友继续创建队友导致生命周期和权限不可控。更复杂的任务协议、审批和关闭握手放到 s16。

### Lead inbox 注入

Lead 需要在“不主动 check inbox”的情况下也能看到队友结果。实现方式是在 hook 层增加 `team_before_model_call_hook`：

1. 每轮模型调用前读取 `lead` 的 inbox。
2. 如果没有消息，不改动当前 messages。
3. 如果有消息，把消息格式化成一条 user 消息追加到当前上下文。
4. 格式建议使用明确边界，避免和用户原始输入混淆：

```text
<team_inbox>
From alice [result]: schema.sql 已创建，包含 users 表。
From bob [message]: 我发现 API 测试需要先补 auth fixture。
</team_inbox>
```

hook 注册顺序建议放在 Memory 召回和 Background/Cron 状态注入之后、模型调用之前。这样 Lead 看到的是“当前用户输入 + 记忆 + 后台状态 + 团队消息”的完整上下文。

同时保留显式工具 `team_check_inbox`，方便 Lead 在需要时主动读取未自动注入的消息，或查询 teammate 自己的 inbox。

### 工具设计

在 `tools_configs/base_configs.py` 追加团队工具 schema：

- `spawn_teammate(name, role, prompt)`：创建 teammate 并开始执行。
- `team_send_message(to, content, msg_type="message")`：向 teammate 或 Lead 发送消息。
- `team_broadcast(content, recipients=None)`：向多个 teammate 广播。
- `team_check_inbox(agent=None)`：读取当前 Agent 或指定 Agent 的 inbox。
- `team_list()`：列出团队成员和状态。

在 `handlers/base_handlers.py` 追加对应 handler，统一调用全局 `TEAM_MANAGER`：

- `handle_spawn_teammate(arguments, context)`
- `handle_team_send_message(arguments, context)`
- `handle_team_broadcast(arguments, context)`
- `handle_team_check_inbox(arguments, context)`
- `handle_team_list(arguments, context)`

权限配置需要把这些工具加入 `configs/permission_config.yml`。建议初版默认允许 `team_list`、`team_check_inbox`、`team_send_message`，而 `spawn_teammate` 可以按现有权限策略配置为允许或询问，因为它会启动新的模型调用线程。

### Prompt 设计

`prompts/team_prompts.py` 分成 Lead 规则和 teammate 规则：

- Lead 规则：可以把大任务拆分给 teammate；分配任务时说明目标、约束、预期产物；收到 teammate 结果后要综合判断，不盲信。
- teammate 规则：只处理自己的任务；必要时向 Lead 提问；阶段性进展用 `team_send_message` 汇报；完成后发送 `result`；不要创建新的 teammate。

`managers/system_prompt_builder.py` 给主 Agent 增加 `team_rules` section。teammate 可以复用现有 subagent prompt builder，也可以新增 `build_teammate_system_prompt(member, workdir)`，但要确保 teammate prompt 不包含创建队友的工具说明。

### 示例流程

用户输入：

```text
重构后端认证模块，一个人搞不定就组队。请让一个队友整理数据库表结构，让另一个队友补 API 测试。
```

Lead 第 1 轮：

1. 调用 `spawn_teammate(name="alice", role="database engineer", prompt="检查认证模块需要的表结构，补充 schema 变更建议。")`。
2. 调用 `spawn_teammate(name="bob", role="backend tester", prompt="检查认证 API 的测试覆盖，补充缺失测试。")`。
3. `TeamManager` 写入 `.team/members.json`，并启动两个 daemon thread。

队友线程并发工作：

```jsonl
{"id":"m1","sender":"alice","recipient":"lead","type":"result","content":"建议新增 user_sessions 表，并给 users.email 加唯一索引。","created_at":"2026-07-08T21:30:00"}
{"id":"m2","sender":"bob","recipient":"lead","type":"result","content":"已补 login/logout/refresh 三类 API 测试，发现 refresh 缺少过期 token 用例。","created_at":"2026-07-08T21:30:02"}
```

Lead 第 2 轮模型调用前：

1. `team_before_model_call_hook` 读取 `.team/inbox/lead.jsonl`。
2. 把 alice 和 bob 的结果注入 `<team_inbox>`。
3. Lead 基于两个队友结果继续汇总、追问或安排下一步。

如果 Lead 需要补充说明，可以调用：

```text
team_send_message(to="bob", content="请优先补 refresh 过期 token 的失败用例。")
```

### 边界与后续演进

- s15 只保证“调度 teammate”与“teammate 执行任务”解耦，不做复杂协议。
- 文件 inbox 会保留未读消息，但 teammate 线程本身不跨进程恢复；进程退出后线程结束。
- 初版使用线程锁即可；跨进程文件锁和消息确认机制放到 s16/s18。
- teammate 的权限请求不在 s15 冒泡到 Lead；先遵循当前项目已有工具权限策略。
- s16 再增加 `shutdown_request`、`shutdown_approved`、`plan_approval_request`、`permission_request` 等结构化协议。

### 验收

- Lead 能调用 `spawn_teammate` 创建 teammate，`.team/members.json` 能看到成员状态。
- teammate 能在独立线程内完成任务，并向 `.team/inbox/lead.jsonl` 写入 `result`。
- Lead 下一轮模型调用前能自动注入 `<team_inbox>`，并基于队友消息继续推理。
- Lead 能通过 `team_send_message` 给 teammate 发送补充消息。
- `team_list` 能列出 teammate 的角色、状态、轮次和最后活跃时间。
- 单个 teammate 异常不会终止 Lead 主循环，错误会以 `error` 消息写回 Lead inbox。

## 19. s16: Team Protocols

主题：队友之间要有约定。s15 已经实现了 Lead + teammate + 文件 inbox，但消息还是松散文本；s16 在此基础上增加 request-response 协议、请求状态追踪和 teammate idle loop。

### 设计目标

- 把团队消息从“普通文本”升级为“结构化协议消息”。
- 支持 `request_id` 关联请求和响应，避免把一个回复误匹配到另一个请求。
- 支持 Lead 请求 teammate 优雅关闭：`shutdown_request -> shutdown_approved/shutdown_rejected -> teammate_terminated`。
- 支持 teammate 提交计划给 Lead 审批：`plan_approval_request -> plan_approval_approved/plan_approval_rejected`。
- 解决 s15 的边界问题：teammate 完成初始任务后不再直接退出，而是进入 idle loop，继续轮询 inbox，直到收到 shutdown 协议。
- 保持当前项目架构：工具 schema 继续进入 `tools_configs/base_configs.py`，handler 继续进入 `handlers/base_handlers.py`，协议状态由 manager 管理，不新增分散的 handler/config 入口。

### 与当前 s15 代码的关系

s15 当前已有：

- `tools/message_bus.py`：`.team/inbox/*.jsonl` 文件收件箱。
- `managers/team_manager.py`：`TEAM_MANAGER` 管理成员、线程和消息。
- `subagents/teammate_agent.py`：teammate 独立 Agent 循环。
- `tools_configs/base_configs.py`：团队工具定义。
- `hooks/builtin_hooks.py`：Lead inbox 注入。

s16 不重做这些基础能力，而是在它们上面增加协议层。推荐新增少量专门模块，同时改造 s15 的 TeamManager 和 teammate loop：

```text
state/
├── team_state.py                   # 扩展 TeamMessage type/metadata 约定
└── team_protocol_state.py          # ProtocolRequestRecord、ProtocolStatus
managers/
├── team_manager.py                 # 接入协议路由、成员状态、idle/shutdown 状态
└── team_protocol_manager.py        # 请求创建、响应匹配、持久化
subagents/
├── teammate_agent.py               # 改为 work -> idle -> shutdown 生命周期
└── team_protocols.py               # teammate 侧协议消息处理
prompts/
├── team_prompts.py                 # 更新 Lead/teammmate 协议规则
└── team_protocol_prompts.py        # 协议消息和审批规则
tools_configs/
└── base_configs.py                 # 追加协议工具 schema，由 base_configs.py 汇总
handlers/
└── base_handlers.py                # 追加协议工具 handler
hooks/
└── builtin_hooks.py                # Lead inbox 先路由协议，再注入普通消息
configs/
└── team_config.yml                 # 增加协议和 idle loop 配置
.team/
├── requests.json                   # pending/resolved request 状态
├── events.jsonl
└── inbox/
```

### 配置扩展

继续使用 `configs/team_config.yml`，避免把团队相关配置拆散：

```yaml
ENABLE_TEAM_PROTOCOLS: true
TEAM_REQUEST_FILE: ".team/requests.json"
TEAM_REQUEST_ID_PREFIX: "team_req_"
TEAM_REQUEST_TIMEOUT_SECONDS: 300
TEAM_IDLE_POLL_SECONDS: 1
TEAM_IDLE_MAX_SECONDS: 0        # 0 表示不因 idle 超时自动退出
TEAM_IDLE_NOTIFY_LEAD: true
PLAN_APPROVAL_REQUIRED: true
PLAN_APPROVAL_MAX_CHARS: 6000
```

### 协议状态结构

新增 `state/team_protocol_state.py`：

```python
@dataclass
class ProtocolRequestRecord:
    request_id: str
    protocol: str              # shutdown / plan_approval
    sender: str
    recipient: str
    status: str                # pending / approved / rejected / expired / cancelled
    request_type: str          # shutdown_request / plan_approval_request
    response_type: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    response: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    resolved_at: str | None = None
```

状态文件 `.team/requests.json` 保存所有未过期请求和最近已完成请求，便于测试和排查。

### 消息类型约定

s16 的 `TeamMessage.type` 不再只靠 `message/result/error`，需要约定协议类型：

| 类型 | 方向 | 作用 |
|---|---|---|
| `idle_notification` | teammate -> Lead | 队友完成一轮工作，进入 idle |
| `shutdown_request` | Lead -> teammate | 请求队友体面退出 |
| `shutdown_approved` | teammate -> Lead | 队友同意退出，并附带收尾摘要 |
| `shutdown_rejected` | teammate -> Lead | 队友暂时拒绝退出，并说明原因 |
| `teammate_terminated` | teammate/system -> Lead | 队友线程已结束 |
| `plan_approval_request` | teammate -> Lead | 队友提交计划，等待审批 |
| `plan_approval_approved` | Lead -> teammate | Lead 批准计划 |
| `plan_approval_rejected` | Lead -> teammate | Lead 拒绝计划，附反馈 |

所有 request/response 类消息必须在 `metadata` 中带：

```json
{
  "request_id": "team_req_000001",
  "protocol": "shutdown"
}
```

计划审批还需要附带 `plan`、`risk_level`、`target_files` 等 payload。shutdown 响应需要附带 `summary` 或 `reason`。

### TeamProtocolManager

新增 `managers/team_protocol_manager.py`，职责是“请求状态机”，不负责真正执行队友任务。

核心 API：

- `ensure_store()`：创建 `.team/requests.json`。
- `create_request(protocol, sender, recipient, request_type, payload)`：生成 `request_id`，写入 pending 记录。
- `match_response(message)`：根据 `request_id` 找 pending 记录，校验协议类型和响应类型，更新为 approved/rejected。
- `list_requests(include_resolved=True)`：查看请求状态。
- `get_request(request_id)`：查看单个请求。
- `expire_old_requests(now=None)`：把超过 `TEAM_REQUEST_TIMEOUT_SECONDS` 的 pending 请求标记为 expired。

匹配规则：

- 找不到 `request_id`：记录 `protocol_unmatched_response` 事件，不更新状态。
- `protocol` 不一致：拒绝匹配。
- 请求不是 pending：忽略重复响应。
- `shutdown_approved` / `plan_approval_approved` -> `approved`。
- `shutdown_rejected` / `plan_approval_rejected` -> `rejected`。

### TeamManager 改造

`managers/team_manager.py` 继续作为 Lead 工具和 teammate 线程的入口，但要增加协议协作方法：

- `request_shutdown(name, reason="")`
  - 创建 `shutdown` request。
  - 向 teammate inbox 发送 `shutdown_request`。
  - 返回 `request_id`。
- `submit_plan(sender, plan, risk_level="", target_files=None)`
  - teammate 调用，创建 `plan_approval` request。
  - 向 Lead inbox 发送 `plan_approval_request`。
- `review_plan(request_id, approve, feedback="")`
  - Lead 调用，根据 request_id 生成 `plan_approval_approved` 或 `plan_approval_rejected`。
  - 发送回原 teammate。
- `protocol_status(request_id=None)`
  - 列出 pending/resolved 协议请求。
- `route_protocol_messages(messages, recipient)`
  - inbox 消费后先处理协议响应，再把普通消息交给 prompt 注入。

Lead 的 inbox 处理顺序必须调整为：

1. `MessageBus.read_inbox("lead")`。
2. 对协议响应调用 `TeamProtocolManager.match_response()`。
3. 对 `plan_approval_request` 保留为可注入消息，让 Lead 模型看到并决定是否 `team_review_plan`。
4. 普通 `message/result/error` 注入 `<team_inbox>`。

### teammate idle loop

当前 s15 中，teammate 在模型返回非 tool call 后会把结果发给 Lead，然后状态改为 `idle` 并返回。s16 要改成真正的生命周期：

```text
starting -> running -> idle -> running -> idle -> shutting_down -> stopped
                      \-> failed
```

行为设计：

1. teammate 完成一轮任务且没有更多 tool call 时：
   - 发送 `result` 给 Lead。
   - 状态改为 `idle`。
   - 可选发送 `idle_notification`。
2. idle loop 每 `TEAM_IDLE_POLL_SECONDS` 读取自己的 inbox。
3. 收到普通 `message` 或 `task_assignment`：
   - 注入 teammate messages。
   - 状态改回 `running`。
   - 继续模型循环。
4. 收到 `shutdown_request`：
   - 如果没有正在执行的工具，发送 `shutdown_approved`。
   - 写入最终摘要。
   - 状态改为 `stopped`。
   - 发送 `teammate_terminated`。
   - 线程退出。
5. 收到 `plan_approval_approved/rejected`：
   - 根据 request_id 唤醒等待中的计划。
   - approved 才继续执行高风险计划。
   - rejected 把 feedback 注入 messages，让 teammate 调整计划或停止。

### 计划审批

计划审批是 s16 的第二个协议示例，重点是 request-response 和 request_id 匹配。

新增 teammate 工具：

- `team_submit_plan(plan, risk_level=None, target_files=None)`
  - 只能由 teammate 使用。
  - 创建 `plan_approval_request`。
  - 将请求发给 Lead。
  - teammate 进入“等待审批”状态，不继续执行该计划。

新增 Lead 工具：

- `team_review_plan(request_id, approve, feedback="")`
  - approve=true：发送 `plan_approval_approved` 给请求发起 teammate。
  - approve=false：发送 `plan_approval_rejected`，并附反馈。

初版可以不做全局执行门控，但 teammate prompt 必须明确：提交计划后，未收到 approved 不要执行计划里的写入、编辑或危险命令。后续如要更严格，可以在 `PreToolUse` hook 中检查 teammate 是否有 pending plan approval，从工具层阻断 `bash/write_file/edit_file`。

### 工具设计

继续在 `tools_configs/base_configs.py` 追加 schema，不新增 `team_protocol_configs.py`：

Lead 可见：

- `team_request_shutdown(name, reason=None)`
- `team_review_plan(request_id, approve, feedback=None)`
- `team_protocol_status(request_id=None, include_resolved=True)`

teammate 可见：

- `team_submit_plan(plan, risk_level=None, target_files=None)`
- `team_protocol_status(request_id=None)`

`handlers/base_handlers.py` 追加：

- `handle_team_request_shutdown(args, runtime_context=None)`
- `handle_team_review_plan(args, runtime_context=None)`
- `handle_team_protocol_status(args, runtime_context=None)`

`subagents/teammate_agent.py` 的 teammate tool dispatcher 追加：

- `team_submit_plan`
- `team_protocol_status`

`handlers/dispatcher.py` 要把新增 Lead 协议工具加入“需要 runtime_context 的工具集合”。

### Prompt 设计

`prompts/team_protocol_prompts.py`：

- Lead 规则：
  - 请求关闭 teammate 时使用 `team_request_shutdown`，不要直接假设线程已经退出。
  - 看到 `plan_approval_request` 后，必须判断风险、目标文件和计划是否清晰，再调用 `team_review_plan`。
  - 审批拒绝必须给出可执行反馈。
- teammate 规则：
  - 完成一轮任务后进入 idle，等待 Lead 新消息或 shutdown。
  - 收到 shutdown_request 时，先收尾，再回复 approved/rejected。
  - 高风险修改前先调用 `team_submit_plan`，等待 approved 后再执行。

`managers/system_prompt_builder.py` 将协议规则并入 `team_rules` 或新增 `team_protocol_rules` section。推荐直接在 `_team_rules_prompt()` 中拼接，避免 section 数量过多。

### 示例流程：优雅关闭

```text
1. Lead 调用 spawn_teammate("alice", "reader", "读取 team_config.yml 并汇报")
2. alice 完成初始任务 -> team_send_message(type=result) -> 状态 idle
3. Lead 调用 team_request_shutdown(name="alice", reason="测试结束")
4. TeamProtocolManager 创建 team_req_000001，状态 pending
5. MessageBus 向 .team/inbox/alice.jsonl 写入 shutdown_request
6. alice idle loop 读取 inbox，处理 shutdown_request
7. alice 发送 shutdown_approved，随后发送 teammate_terminated
8. Lead 下一轮读取 lead inbox，match_response 把 team_req_000001 标记为 approved
9. team_protocol_status 显示 shutdown 请求已 approved，alice 状态 stopped
```

### 示例流程：计划审批

```text
1. bob 准备重构认证模块，判断会修改多个文件
2. bob 调用 team_submit_plan(plan="...", risk_level="high", target_files=[...])
3. TeamProtocolManager 创建 team_req_000002，状态 pending
4. Lead 收到 plan_approval_request，模型审查计划
5. Lead 调用 team_review_plan(request_id="team_req_000002", approve=false, feedback="先补测试再改实现")
6. bob idle loop 收到 plan_approval_rejected，把 feedback 注入上下文
7. bob 修改计划后可再次 submit_plan
```

### 相对 s15 的变化

| 组件 | s15 | s16 |
|---|---|---|
| 消息 | 普通 message/result/error | 增加结构化协议类型 |
| 请求状态 | 无 | `.team/requests.json` + `TeamProtocolManager` |
| teammate 生命周期 | 完成后 idle 但线程退出 | idle loop 持续等待 inbox |
| 关闭 | 无协议，无法体面停止 | `shutdown_request` 握手 |
| 计划审批 | 无 | `plan_approval_request` + review |
| Lead inbox | 直接注入 | 先路由协议，再注入普通消息 |
| 工具 | 团队创建和消息工具 | 增加 shutdown、review、status、submit_plan |

### 验收

- Lead 能创建 teammate，teammate 完成任务后保持 idle 线程，而不是直接退出。
- `team_request_shutdown("alice")` 会生成 request_id，并向 alice inbox 写入 `shutdown_request`。
- alice 收到 shutdown 请求后，发送 `shutdown_approved` 或 `shutdown_rejected`。
- Lead 消费 inbox 后，`.team/requests.json` 中对应 request 从 pending 变为 approved/rejected。
- teammate 退出时成员状态更新为 `stopped`，并写入 `teammate_terminated` 事件。
- teammate 能调用 `team_submit_plan` 创建计划审批请求。
- Lead 能调用 `team_review_plan` 批准或拒绝计划，response 能按 request_id 精确回到发起 teammate。
- 重复 response、错误 request_id、协议类型不匹配不会错误更新 pending request。
- `team_protocol_status` 能展示 pending/resolved 请求，便于测试和排查。

## 20. s17: Autonomous Agents

主题：自己看板，自己认领。s16 已经让 teammate 在 idle loop 中等待 inbox 和 shutdown；s17 在 idle loop 中再加入“扫描任务看板、自动认领、执行、完成”的自治能力，让 Lead 只负责创建任务和启动队友。

### 设计目标

- idle teammate 不只等待 Lead 消息，还会主动扫描 `.tasks/` 看板。
- teammate 能自动发现 ready 的 pending 任务，并用自己的名字作为 owner 认领。
- 认领成功后，teammate 把任务内容注入自己的 messages，回到 running 状态执行。
- 完成任务后，teammate 调用 `task_complete` 更新任务状态，并通过团队消息通知 Lead。
- 多个 teammate 并发扫描时，同一个任务只能被一个 teammate 认领。
- 保持当前项目架构：复用 `TASK_MANAGER` 的持久任务系统，复用 s16 的 teammate idle loop 和 Team Protocols，不新增独立的任务存储。

### 与当前代码的关系

当前项目已有：

- `managers/task_manager.py`
  - `create()` 创建持久任务。
  - `list_all()` 展示任务看板。
  - `claim(task_id, owner)` 已有 owner 检查、pending 检查和依赖完成检查。
  - `complete(task_id, owner, summary)` 完成任务，并返回解锁的下游任务。
  - 内部已有 `_task_lock(task_id)`，认领和完成发生在任务锁内。
- `subagents/teammate_agent.py`
  - s16 已有 `_idle_until_message(...)`，idle 时轮询 inbox。
  - s16 已有 shutdown 和 plan approval 协议处理。
- `managers/team_manager.py`
  - 维护 teammate 状态。
  - 能向 Lead 发送 `idle_notification`、`result`、`error` 等消息。

s17 不重写任务系统，而是在 teammate idle 阶段接入任务扫描和自动 claim。

建议新增和修改：

```text
configs/
└── team_config.yml                 # 增加自治开关和轮询配置
state/
└── autonomous_state.py             # 可选，定义 AutonomousClaimAttempt
managers/
├── autonomous_manager.py           # 自动扫描、选择、认领任务
├── task_manager.py                 # 复用现有 claim/complete；必要时增加 find_ready_tasks()
└── team_manager.py                 # 记录 teammate 自治事件和状态
subagents/
├── teammate_agent.py               # idle loop 增加 scan/claim 分支
└── team_protocols.py               # shutdown 仍优先于 auto-claim
tools_configs/
└── team_configs.py                 # 给 teammate 增加任务工具 schema
handlers/
└── base_handlers.py                # 可选，Lead 侧增加 autonomous status 工具
.team/
└── autonomous_events.jsonl         # 自动认领审计事件
```

### 配置设计

继续扩展 `configs/team_config.yml`：

```yaml
ENABLE_AUTONOMOUS_AGENTS: true
AUTONOMOUS_TASK_SCAN_ENABLED: true
AUTONOMOUS_IDLE_SCAN_SECONDS: 5
AUTONOMOUS_IDLE_TIMEOUT_SECONDS: 60
AUTONOMOUS_MAX_CLAIMS_PER_IDLE: 1
AUTONOMOUS_EVENT_FILE: ".team/autonomous_events.jsonl"
AUTONOMOUS_REQUIRE_TASK_METADATA_MATCH: false
AUTONOMOUS_ROLE_METADATA_KEY: "role"
AUTONOMOUS_ALLOWED_STATUSES:
  - pending
AUTONOMOUS_NOTIFY_LEAD_ON_CLAIM: true
AUTONOMOUS_NOTIFY_LEAD_ON_COMPLETE: true
```

含义：

- `AUTONOMOUS_IDLE_SCAN_SECONDS`：idle 状态扫描任务板的间隔。
- `AUTONOMOUS_IDLE_TIMEOUT_SECONDS`：无 inbox、无可认领任务时多久退出；如果希望 teammate 常驻，可设为 `0`。
- `AUTONOMOUS_MAX_CLAIMS_PER_IDLE`：一次 idle 扫描最多认领几个任务，初版建议为 1。
- `AUTONOMOUS_REQUIRE_TASK_METADATA_MATCH`：是否按任务 metadata 和 teammate role 过滤任务；初版默认 false，避免过早复杂化。

### AutonomousManager

新增 `managers/autonomous_manager.py`，只负责“找任务”和“尝试认领”，不负责具体执行任务。

核心 API：

- `ensure_store()`：创建 `.team/autonomous_events.jsonl`。
- `scan_ready_tasks(teammate_name, role="") -> list[TaskRecord]`
  - 从 `TASK_MANAGER` 读取所有任务。
  - 过滤 `status == "pending"`。
  - 过滤 `owner is None`。
  - 过滤依赖未完成的任务。
  - 可选按 metadata role 匹配。
- `try_claim_next(teammate_name, role="") -> ClaimResult`
  - 按排序选择一个 ready 任务。
  - 调用 `TASK_MANAGER.claim(task.id, owner=teammate_name)`。
  - 判断返回结果是否以“已认领”开头。
  - 记录 `claim_attempt` / `claim_success` / `claim_failed` 事件。
- `format_task_assignment(task) -> str`
  - 把任务转换成 teammate 可执行的 `<claimed_task>` 上下文。
- `record_complete(teammate_name, task_id, summary)`
  - 调用 `TASK_MANAGER.complete(task_id, owner=teammate_name, summary=summary)`。
  - 记录完成事件并通知 Lead。

`TASK_MANAGER.claim()` 已经在任务锁里做检查，因此 AutonomousManager 不再自己实现一套写文件逻辑。并发时，如果 alice 和 bob 同时扫描到同一个任务，只有先拿到锁并写入 owner 的那个会成功，另一个会收到“已被 xxx 认领”。

### 任务筛选规则

ready 任务定义：

```text
status == pending
owner is empty
all blocked_by dependencies are completed
not cancelled
```

这和 `TaskManager._readiness()` 中的 ready/blocked 语义保持一致。不要把“有 blocked_by”简单等同于 blocked；只有依赖任务未完成时才 blocked。

排序规则建议沿用 `TaskManager._sorted_tasks()`：

1. ready pending
2. blocked pending
3. completed
4. cancelled

s17 只认领 ready pending。

### teammate idle loop 改造

s16 的 `_idle_until_message(...)` 当前逻辑是：

```text
idle:
  1. 读取自己的 inbox
  2. 收到 shutdown -> 退出
  3. 收到普通消息 -> running
  4. 否则 sleep
```

s17 改为：

```text
idle:
  1. 读取自己的 inbox，优先处理 shutdown / plan response / 普通消息
  2. 如果 inbox 没有工作，调用 AUTONOMOUS_MANAGER.try_claim_next(member.name, member.role)
  3. 如果认领成功，把 <claimed_task> 注入 teammate messages
  4. 状态改为 running，回到模型循环
  5. 如果没有可认领任务，sleep AUTONOMOUS_IDLE_SCAN_SECONDS
  6. 超过 AUTONOMOUS_IDLE_TIMEOUT_SECONDS 且没有新任务，则 stopped 或继续 idle，取决于配置
```

inbox 优先级必须高于任务板，原因是 shutdown 和审批响应不能被自动认领任务饿死。

### teammate 可用任务工具

s17 需要给 teammate 增加任务工具，但不让 teammate 创建任意大任务图。建议只开放执行自己任务所需的最小工具：

- `task_list`
  - 查看任务看板，辅助模型理解上下文。
- `task_get`
  - 读取自己认领任务的完整说明。
- `task_complete`
  - 完成自己 owner 的任务。

可选新增封装工具：

- `autonomous_current_task`
  - 返回当前 teammate 认领的任务。
- `autonomous_scan_tasks`
  - 手动触发一次扫描，主要用于测试。

更推荐初版不新增 Lead 可见工具，只把这些 teammate 工具加入 `TEAMMATE_AVAILABLE_TOOLS`，由 teammate 的 idle loop 自动注入 `<claimed_task>`。

### 当前任务上下文

teammate 认领成功后，向自己的 messages 注入：

```text
<claimed_task>
id: task_000003
subject: 编写认证 API 测试
description:
...
owner: protocol_bob
blocked_by: -

你已经成功认领该任务。请完成它，完成后调用 task_complete(task_id="task_000003", owner="protocol_bob", summary="...")。
</claimed_task>
```

同时向 Lead 发一条 `task_claimed` 或普通 `message`：

```text
protocol_bob 已自动认领 task_000003：编写认证 API 测试
```

完成后向 Lead 发 `result`：

```text
protocol_bob 已完成 task_000003：...
```

### 自动完成策略

任务是否完成必须由 teammate 模型判断，不由 idle loop 自动完成。原因是 idle loop 只能认领任务，不能知道任务是否真的完成。

teammate 执行任务时应：

1. 根据 `<claimed_task>` 做实际读取、修改、测试或总结。
2. 必要时走 s16 的 `team_submit_plan` 审批。
3. 完成后调用 `task_complete(task_id, owner=<teammate>, summary=...)`。
4. 再通过 `team_send_message(to="lead", msg_type="result", content=...)` 汇报。
5. 回到 idle，继续扫描下一个 ready 任务。

### 与 Team Protocols 的优先级

s17 必须保持 s16 协议优先：

1. `shutdown_request` 最高优先级，收到后不再认领新任务。
2. `plan_approval_approved/rejected` 优先于自动扫描任务，因为它可能解锁当前正在等待的工作。
3. 普通 Lead 消息优先于自动任务认领。
4. 只有 inbox 没有可处理消息时，才扫描任务看板。

### Lead 的角色变化

s17 后，Lead 不需要逐个分配任务。Lead 的职责变为：

- 创建任务图：`task_create`，设置 `blocked_by`。
- 启动 teammate：`spawn_teammate`。
- 审批计划：`team_review_plan`。
- 处理关闭：`team_request_shutdown`。
- 汇总结果：读取 `<team_inbox>`、`team_list`、`task_list`。

Lead 不再需要对每个 teammate 发送“你去做 task_xxx”的消息。

### 示例流程

```text
1. Lead 创建任务：
   - task_000001：整理认证配置
   - task_000002：补充登录测试，依赖 task_000001
   - task_000003：编写接口说明，依赖 task_000001

2. Lead 启动两个 teammate：
   - auto_alice，role=backend engineer
   - auto_bob，role=test engineer

3. auto_alice 初始任务完成后进入 idle。
4. idle loop 扫描 `.tasks/`，发现 task_000001 ready。
5. auto_alice 调用 TASK_MANAGER.claim(task_000001, owner=auto_alice)，认领成功。
6. auto_bob 同时扫描，但 task_000001 已有 owner；它不会覆盖，继续 idle。
7. auto_alice 完成 task_000001，调用 task_complete。
8. task_000002/task_000003 依赖解锁。
9. auto_alice 和 auto_bob 下一轮 idle 扫描分别认领不同任务。
10. 所有任务完成后，Lead 通过 team inbox 收到结果摘要。
```

### 文件和事件

新增 `.team/autonomous_events.jsonl`：

```jsonl
{"type":"scan","teammate":"auto_alice","ready_count":1,"created_at":"..."}
{"type":"claim_success","teammate":"auto_alice","task_id":"task_000001","created_at":"..."}
{"type":"claim_failed","teammate":"auto_bob","task_id":"task_000001","reason":"已被 auto_alice 认领","created_at":"..."}
{"type":"complete","teammate":"auto_alice","task_id":"task_000001","created_at":"..."}
```

任务本身仍保存在 `.tasks/task_*.json`；任务事件仍由 `TASK_MANAGER.append_event(...)` 写入任务系统自己的事件文件。

### Prompt 设计

扩展 `prompts/team_prompts.py` 或新增 `prompts/autonomous_prompts.py`：

Lead 规则：

- 大目标优先拆成 task graph，再启动 teammate。
- 不要手动把每个任务发给 teammate；让 teammate idle 后自己认领。
- 用 `task_list` 和 `team_list` 查看进度。

teammate 规则：

- idle 时可以自动认领 ready 任务。
- 只完成 owner 是自己的任务。
- 完成任务必须调用 `task_complete`，不要只发消息。
- 如果任务涉及高风险写入，先走 s16 `team_submit_plan`。
- 收到 shutdown_request 后停止认领新任务。

### 验收

- idle teammate 在没有 inbox 消息时会扫描 `.tasks/`。
- ready pending 且无 owner 的任务能被 teammate 自动认领。
- 被未完成依赖阻塞的任务不会被认领。
- 两个 teammate 并发扫描时，同一个任务不会被重复认领。
- 认领成功后，任务文件状态变为 `in_progress`，owner 为 teammate 名称。
- teammate 完成任务后能调用 `task_complete`，任务状态变为 `completed`。
- 完成上游任务后，下游任务会在下一轮扫描中变为可认领。
- 收到 `shutdown_request` 后，teammate 不再认领新任务。
- `.team/autonomous_events.jsonl` 能审计 scan/claim/complete。

### 当前实现风险

- 当前 `TaskManager.claim()` 已有任务级锁，但如果后续增加“先扫描再批量认领”，必须避免 scan 和 claim 之间的 TOCTOU 被误认为成功；最终成功只能以 `TASK_MANAGER.claim()` 返回结果为准。
- teammate 工具开放 `task_complete` 后，要确保 owner 校验生效；当前 `REQUIRE_OWNER_TO_COMPLETE` 配置已存在，应保持开启。
- 如果 `AUTONOMOUS_IDLE_TIMEOUT_SECONDS=0` 表示常驻，测试时需要通过 `team_request_shutdown` 主动关闭 teammate。

## 21. s18: Worktree Isolation

主题：各干各的，互不干扰。

目标：

- 在 s17 Autonomous Agents 的基础上，为被认领的持久任务提供独立工作目录。
- Lead 可以提前为任务创建并绑定 git worktree，teammate 自动认领任务后在对应 worktree 中执行文件和命令工具。
- 调度、执行、文件修改互相解耦：任务系统负责“做什么”，自治队友负责“谁来做”，worktree 系统负责“在哪做”。
- worktree 生命周期可审计，可选择保留用于 review，也可在安全检查通过后删除。

### 为什么需要 s18

s17 已经能让 teammate 自己扫描看板、认领 ready task、调用 `task_complete` 完成闭环。但所有 teammate 仍共享同一个 `WORKDIR`。当两个 teammate 并行修改同一文件时，会出现三个问题：

- 改动互相覆盖：alice 和 bob 都写 `config.py`，最后只能保留一个结果。
- 难以审查：无法直接看出某个任务产生了哪些文件改动。
- 难以回滚：无法只丢弃某个 teammate 的实验性改动。

s18 引入 git worktree，让每个任务可以绑定独立目录和独立分支。例如：

- `task_000021` 绑定 `.worktrees/auth-refactor`，分支 `wt/auth-refactor`。
- `task_000022` 绑定 `.worktrees/ui-login`，分支 `wt/ui-login`。

teammate 认领任务后，`bash`、`read_file`、`write_file`、`edit_file` 默认在任务绑定的 worktree 中执行，从而避免并行 teammate 直接争抢主工作区。

### 当前项目落点

s18 不重写 s12/s15/s17，而是在现有结构上增加隔离层：

| 已有能力 | s18 接入方式 |
|---|---|
| `TaskManager` | 任务 metadata 中保存 worktree 绑定信息，不新增并行任务模型 |
| `AutonomousManager` | 认领成功后读取任务 metadata，生成带 worktree 信息的 `<claimed_task>` |
| `run_teammate_agent` | 为 teammate 增加当前 worktree 上下文，工具执行时按上下文切换 cwd |
| `MessageBus` | 继续用于 Lead 和 teammate 通知，不承载 worktree 状态 |
| `permission_config.yml` | 新增 worktree 工具权限，危险删除默认走权限策略 |

设计原则：

- worktree 绑定不改变任务状态。任务仍由 `TASK_MANAGER.claim()` 从 `pending` 推进到 `in_progress`。
- worktree 管理只负责目录、分支和审计，不替代任务完成语义。
- `task_complete` 仍是任务闭环的唯一完成入口。
- 删除 worktree 必须保守：存在未提交改动时默认拒绝，除非显式 `discard_changes=true`。

### 文件设计

```text
configs/
└── worktree_config.yml              # worktree 根目录、分支前缀、安全策略
state/
└── worktree_state.py                # WorktreeRecord 数据结构
managers/
└── worktree_manager.py              # 创建、绑定、状态、保留、删除
tools_configs/
└── worktree_configs.py              # Lead 可用 worktree 工具 schema
handlers/
└── worktree_handlers.py             # 工具 handler，转发给 WORKTREE_MANAGER
utils/
└── git_utils.py                     # git 命令封装、仓库检测、分支名规范化
.worktrees/
├── index.json                       # worktree 索引
├── events.jsonl                     # worktree 生命周期事件
└── <worktree-name>/                 # git worktree 工作目录
```

如果想减少文件数量，`worktree_handlers.py` 也可以先不单独创建，而是像当前 task/team 工具一样注册到 `handlers/base_handlers.py`；但从 s18 开始建议拆出独立 handler，避免 `base_handlers.py` 继续膨胀。

### 配置设计

新增 `configs/worktree_config.yml`，并在 `utils/config_handler.py` 增加 `DEFAULT_WORKTREE_CONFIG` 和 `worktree_config`：

```yaml
ENABLE_WORKTREE_ISOLATION: true
WORKTREE_ROOT: ".worktrees"
WORKTREE_BRANCH_PREFIX: "wt/"
WORKTREE_INDEX_FILE: ".worktrees/index.json"
WORKTREE_EVENT_FILE: ".worktrees/events.jsonl"
WORKTREE_NAME_PATTERN: "^[A-Za-z0-9._-]{1,64}$"
WORKTREE_BASE_REF: "HEAD"
WORKTREE_ALLOW_CREATE_WITH_DIRTY_REPO: false
WORKTREE_REMOVE_REQUIRES_CLEAN: true
WORKTREE_BIND_METADATA_KEY: "worktree"
WORKTREE_AUTO_ENTER_ON_CLAIM: true
WORKTREE_NOTIFY_LEAD_ON_BIND: true
```

含义：

| 配置 | 说明 |
|---|---|
| `ENABLE_WORKTREE_ISOLATION` | 总开关 |
| `WORKTREE_ROOT` | worktree 目录根路径 |
| `WORKTREE_BRANCH_PREFIX` | 自动创建分支名前缀 |
| `WORKTREE_BASE_REF` | 默认从哪个 ref 创建 worktree |
| `WORKTREE_ALLOW_CREATE_WITH_DIRTY_REPO` | 主仓库有未提交改动时是否允许创建 |
| `WORKTREE_REMOVE_REQUIRES_CLEAN` | 删除前是否要求 worktree 无改动 |
| `WORKTREE_BIND_METADATA_KEY` | 写入 task metadata 的 key，默认 `worktree` |
| `WORKTREE_AUTO_ENTER_ON_CLAIM` | teammate 认领绑定任务后是否自动切换工具 cwd |

### 状态结构

新增 `state/worktree_state.py`：

```python
@dataclass
class WorktreeRecord:
    name: str
    path: str
    branch: str
    base_ref: str = "HEAD"
    task_id: str = ""
    status: str = "active"  # active/kept/removed/failed
    created_at: str = ""
    updated_at: str = ""
    metadata: dict = field(default_factory=dict)
```

`.worktrees/index.json`：

```json
{
  "worktrees": [
    {
      "name": "auth-refactor",
      "path": ".worktrees/auth-refactor",
      "branch": "wt/auth-refactor",
      "base_ref": "HEAD",
      "task_id": "task_000021",
      "status": "active",
      "created_at": "...",
      "updated_at": "...",
      "metadata": {}
    }
  ]
}
```

`.worktrees/events.jsonl` 记录：

- `create`
- `bind_task`
- `status`
- `keep`
- `remove`
- `remove_rejected`
- `git_error`
- `auto_enter`

### WorktreeManager

新增 `managers/worktree_manager.py`，全局实例 `WORKTREE_MANAGER`。

核心 API：

```python
class WorktreeManager:
    def ensure_store(self) -> None: ...
    def create(self, name: str, task_id: str = "", base_ref: str = "") -> str: ...
    def bind_task(self, task_id: str, name: str) -> str: ...
    def get_for_task(self, task_id: str) -> Optional[WorktreeRecord]: ...
    def resolve_task_workdir(self, task_id: str) -> Optional[str]: ...
    def list_all(self, include_removed: bool = False) -> str: ...
    def status(self, name: str) -> str: ...
    def keep(self, name: str, reason: str = "") -> str: ...
    def remove(self, name: str, discard_changes: bool = False) -> str: ...
```

创建流程：

1. 校验 `ENABLE_WORKTREE_ISOLATION`。
2. 校验 name，只允许 `[A-Za-z0-9._-]`，拒绝 `.`、`..`、空字符串和路径分隔符。
3. 确认当前项目是 git 仓库；如果不是，返回明确错误。
4. 如果 `WORKTREE_ALLOW_CREATE_WITH_DIRTY_REPO=false`，先检查主仓库是否干净。当前项目开发过程中可能存在未提交改动，初版可以把该配置默认设为 `true`，但文档推荐保守默认。
5. 执行：

```text
git worktree add <WORKTREE_ROOT>/<name> -b <WORKTREE_BRANCH_PREFIX><name> <base_ref>
```

6. 写 `.worktrees/index.json`。
7. 如果传入 `task_id`，调用 `bind_task(task_id, name)`。
8. 写 `create` 事件。

绑定流程：

1. 加载任务。
2. 确认 worktree 存在且未 removed。
3. 调用 `TASK_MANAGER.update(task_id, {"metadata": ...})` 或新增更细的 `set_metadata()` 方法。
4. 在任务 metadata 中写：

```json
{
  "worktree": {
    "name": "auth-refactor",
    "path": ".worktrees/auth-refactor",
    "branch": "wt/auth-refactor"
  }
}
```

如果当前 `TaskManager.update()` 不支持合并 metadata，s18 实现时应新增 `TaskManager.set_metadata(task_id, key, value)`，避免覆盖已有 metadata。

### 工具设计

新增 `tools_configs/worktree_configs.py`：

Lead 工具：

- `worktree_create(name, task_id="", base_ref="")`
- `worktree_bind(task_id, name)`
- `worktree_list(include_removed=false)`
- `worktree_status(name)`
- `worktree_keep(name, reason="")`
- `worktree_remove(name, discard_changes=false)`

不建议给 Lead 暴露 `worktree_run` 作为长期主路径，因为当前项目已经有 `bash`。如果需要调试，可加只读/低风险版本：

- `worktree_run(name, command)`：默认只允许 `pwd`、`git status`、`git diff --stat` 这类诊断命令，或统一走现有权限 gate。

teammate 不需要直接调用 `worktree_create/remove`。teammate 的隔离应来自“认领任务后自动切换 cwd”，而不是让 teammate 自己管理 worktree 生命周期。

handler 注册：

- `handlers/worktree_handlers.py` 实现 `handle_worktree_create` 等函数。
- `handlers/dispatcher.py` 引入 `WORKTREE_HANDLERS`。
- `configs/permission_config.yml` 增加 worktree 工具：
  - `worktree_list`、`worktree_status` 默认允许。
  - `worktree_create`、`worktree_bind` 可默认允许或询问。
  - `worktree_remove` 默认询问，且 `discard_changes=true` 必须更谨慎。

### teammate 如何进入 worktree

s17 的自动认领发生在 `subagents/teammate_agent.py::_idle_until_message()`：

```python
claim_result = AUTONOMOUS_MANAGER.try_claim_next(member.name, role=member.role)
if claim_result.claimed and claim_result.task:
    state.messages.append({
        "role": "user",
        "content": AUTONOMOUS_MANAGER.format_claimed_task(claim_result.task, member.name),
    })
```

s18 在这里追加 worktree 上下文：

1. 认领成功后读取 `claim_result.task.metadata["worktree"]`。
2. 如果存在绑定，并且 `WORKTREE_AUTO_ENTER_ON_CLAIM=true`：
   - 验证 worktree 记录仍 active。
   - 把当前 teammate 的 runtime workdir 设置为 worktree path。
   - 写入 `auto_enter` 事件。
   - 在 `<claimed_task>` 中提示当前工作目录已切换。
3. 如果没有绑定，则继续使用原 `WORKDIR`。

实现上不要调用全局 `os.chdir()`。当前项目有多个 teammate 线程，进程级 cwd 会影响所有线程。应把 workdir 放入 teammate 的局部运行上下文，例如：

```python
state.metadata["current_workdir"] = worktree_path
```

或新增轻量对象：

```python
class TeammateRuntime:
    current_workdir: str
    original_workdir: str
    current_task_id: str
```

然后 `_dispatch_teammate_tool()` 执行文件和命令工具时使用 `current_workdir`：

- `bash`：调用支持 cwd 的命令执行函数。
- `read_file` / `write_file` / `edit_file`：以 `current_workdir` 为沙箱根目录解析路径。

当前 `tools/file_tools.py` 和 `tools/bash_tools.py` 如果只使用进程 cwd，需要在 s18 做小改造：增加可选 `base_dir` / `cwd` 参数，默认仍为原工作区，teammate 调用时传入当前 worktree。

### 文件沙箱边界

引入 worktree 后，路径安全必须重新定义：

- 主 Agent 的文件工具仍以主 `WORKDIR` 为根。
- 认领了 worktree 任务的 teammate 文件工具以 worktree path 为根。
- teammate 不能通过 `..` 跳出 worktree。
- worktree path 必须由 `WorktreeManager` 从索引中解析，不能直接信任模型传入路径。

建议新增 `utils/path_sandbox.py` 的一个辅助函数：

```python
def safe_path_under(root: Path, user_path: str) -> Path:
    ...
```

当前已有 `safe_path()` 时，不要破坏原行为；新增函数用于 s18 的多根沙箱。

### 和任务系统的关系

任务状态仍然只由 `TaskManager` 管理：

- `worktree_create(task_id=...)` 只写 metadata，不 claim。
- `AutonomousManager.try_claim_next()` 仍调用 `TASK_MANAGER.claim()`。
- `task_complete` 仍调用 `TASK_MANAGER.complete()`。
- `worktree_keep/remove` 不自动 complete task。

这样避免 worktree 生命周期和任务生命周期互相绑死。一个任务可以完成但 worktree 保留用于 review；也可以任务失败但 worktree 保留用于排查。

### closeout：keep / remove

`worktree_keep(name, reason)`：

- 把 index 中状态标记为 `kept`。
- 不删除目录、不删除分支。
- 写 `keep` 事件。
- 返回 worktree path、branch、task_id，方便用户 review。

`worktree_remove(name, discard_changes=false)`：

1. 找到 worktree record。
2. 执行 `git -C <path> status --porcelain`。
3. 如果有改动且 `discard_changes=false`，拒绝删除并写 `remove_rejected`。
4. 如果允许删除，执行：

```text
git worktree remove <path> --force
git branch -D <branch>
```

5. index 标记为 `removed`。
6. 写 `remove` 事件。

注意：删除 worktree 是破坏性操作，即使用户要求实现时，也应通过权限系统或明确参数保护。

### Lead 使用示例

用户说：

> 把登录重构拆成两个并行任务，让队友各自在隔离目录里完成。

Lead 的理想流程：

1. `task_create(subject="重构认证服务", description="...", metadata={"role": "backend"})`。
2. `task_create(subject="重构登录页面", description="...", metadata={"role": "frontend"})`。
3. `worktree_create(name="auth-refactor", task_id="task_000021")`。
4. `worktree_create(name="ui-login", task_id="task_000022")`。
5. `spawn_teammate(name="alice", role="backend engineer", prompt="进入 idle 后认领 ready 后端任务，完成后 task_complete 并汇报。")`。
6. `spawn_teammate(name="bob", role="frontend engineer", prompt="进入 idle 后认领 ready 前端任务，完成后 task_complete 并汇报。")`。
7. alice idle 后认领 `task_000021`，自动进入 `.worktrees/auth-refactor`。
8. bob idle 后认领 `task_000022`，自动进入 `.worktrees/ui-login`。
9. Lead 查看 `.team/events.jsonl`、`.team/autonomous_events.jsonl`、`.worktrees/events.jsonl`。
10. Review 后对每个 worktree 调用 `worktree_keep` 或 `worktree_remove`。

### 系统提示词更新

`prompts/team_prompts.py` 增加两条规则：

- Lead：当用户要求并行修改代码、隔离实验、避免互相覆盖时，优先为任务创建 worktree 并绑定 task，再启动 teammate。
- teammate：如果 `<claimed_task>` 指明 worktree 已切换，你的文件和命令工具会在该隔离目录中执行；不要假设自己在主工作区。

`managers/system_prompt_builder.py` 可增加 `worktree_rules` section，说明当前是否启用 worktree isolation，以及 Lead 可用工具。

### 验收标准

1. `worktree_create(name, task_id)` 能在 `.worktrees/<name>` 创建 git worktree 和 `wt/<name>` 分支。
2. `.worktrees/index.json` 能记录 name、path、branch、task_id、status。
3. 任务 JSON 的 `metadata.worktree` 能看到绑定信息，绑定不改变任务状态。
4. teammate 自动认领带 worktree metadata 的任务后，`bash pwd`、`read_file`、`write_file` 在 worktree 目录下执行。
5. 两个 teammate 认领两个不同任务时，写同名文件不会互相覆盖。
6. `task_complete` 成功后，任务系统和自治事件照常写入。
7. `worktree_status` 能展示 git status 和分支。
8. 有未提交改动时，`worktree_remove(discard_changes=false)` 拒绝删除。
9. `worktree_keep` 保留目录和分支，并记录审计事件。
10. `.worktrees/events.jsonl` 能串起 create、bind_task、auto_enter、keep/remove。

### 风险和边界

- 当前目录如果不是 git 仓库，worktree 工具应返回明确错误，不应降级成普通目录复制。
- 不使用 `os.chdir()` 切换 teammate cwd，因为当前项目是多线程 teammate，进程级 cwd 会污染其他线程。
- worktree 删除是破坏性操作，必须有干净检查和权限保护。
- 不把 worktree path 直接暴露成模型可自由传入的根路径，必须从 manager 索引解析。
- 如果任务没有绑定 worktree，s17 行为保持不变，teammate 在主 `WORKDIR` 执行。
- 如果 `git worktree add` 失败，不写成功事件，也不绑定 task metadata。

## 22. s19: MCP Tools

主题：外接工具，标准协议。

目标：

- 支持 MCP server 发现和工具路由。
- 本地工具和 MCP 工具组装为统一工具池。

要完成什么：

- 加载插件配置。
- 连接 MCP server。
- 发现 MCP tools。
- 规范化工具名为 `mcp__server__tool`。
- MCP 调用经过权限 gate。

文件设计：

```text
mcp/
├── __init__.py
├── plugin_loader.py
├── mcp_client.py
├── mcp_tool_router.py
├── tool_pool.py
└── capability_permission_gate.py
tools_configs/
└── mcp_configs.py
handlers/
└── mcp_handlers.py
configs/
└── mcp_config.yml
```

实现内容：

- `mcp/plugin_loader.py`
  - 读取插件或 MCP server 配置。
- `mcp/mcp_client.py`
  - 管理 MCP 连接。
- `mcp/mcp_tool_router.py`
  - 根据 `mcp__server__tool` 路由调用。
- `mcp/tool_pool.py`
  - 合并本地工具和 MCP 工具。
  - 本地工具名冲突时本地优先。
- `mcp/capability_permission_gate.py`
  - MCP 工具权限判断。
- `handlers/mcp_handlers.py`
  - MCP 工具执行入口。

验收：

- 没有 MCP server 时，本地工具仍可运行。
- MCP 工具可以出现在工具列表中。
- MCP 调用失败返回结构化错误，不杀掉主循环。
