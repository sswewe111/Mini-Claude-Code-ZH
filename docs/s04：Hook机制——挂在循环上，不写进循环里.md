# s04：Hook机制——挂在循环上，不写进循环里

s01 → s02 → s03 → `s04` → s05 → ... → s20

> Hook 的作用是在固定时机扩展 Agent 行为。主循环只暴露事件，具体日志、权限、工具前后处理都挂到 hook 上。

---

## 问题

s03 已经有权限控制，但如果继续把日志、权限、输出检查都写进 `agent_loop.py` 或 `dispatcher.py`，主流程会越来越难维护。

当前项目的目标是：

- `agent_loop.py` 只负责模型循环。
- `handlers/dispatcher.py` 只负责工具分发。
- `hooks/` 负责扩展逻辑。
- s03 的权限检查也作为 final `PreToolUse` hook 运行。

---

## 当前文件

```text
configs/
└── hooks_config.yml

state/
└── hook_state.py

hooks/
├── builtin_hooks.py
└── hook_manager.py

handlers/
└── dispatcher.py

agent_loop.py
```

各文件职责：

- `configs/hooks_config.yml`：配置外部命令 hook，当前默认关闭。
- `state/hook_state.py`：定义 `HookContext` 和 `HookResult`。
- `hooks/hook_manager.py`：注册、匹配、执行 hook。
- `hooks/builtin_hooks.py`：内置日志 hook 和权限检查 hook。
- `handlers/dispatcher.py`：触发 `PreToolUse` 和 `PostToolUse`。
- `agent_loop.py`：触发生命周期 hook。

---

## Hook 事件

当前 `HookManager` 支持六个事件：

| 事件 | 触发位置 | 当前用途 |
|------|----------|----------|
| `SessionStart` | `main()` 启动后 | 记录 Agent 会话启动 |
| `BeforeModelCall` | 调用模型前 | 记录模型名、消息数量 |
| `AfterModelCall` | 模型返回后 | 记录停止原因、工具调用数量 |
| `PreToolUse` | 工具执行前 | 日志、权限检查、阻止工具 |
| `PostToolUse` | 工具执行后 | 记录输出长度、可改写输出 |
| `Stop` | Agent 返回最终答案前 | 预留收尾扩展点 |

当前内置 hook 没有注册 `Stop` 处理函数，但 `agent_loop.py` 已经触发了 `Stop` 事件，后续可以注册自定义 hook。

---

## HookContext 和 HookResult

`state/hook_state.py` 用两个 dataclass 统一 hook 输入输出。

`HookContext` 是 hook 的上下文：

```python
@dataclass
class HookContext:
    event: str
    tool_name: Optional[str] = None
    tool_input: Dict[str, Any] = field(default_factory=dict)
    tool_output: Optional[str] = None
    messages: Optional[list] = None
    model_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
```

`HookResult` 是 hook 的结构化结果：

```python
@dataclass
class HookResult:
    blocked: bool = False
    block_reason: str = ""
    updated_output: Optional[str] = None
    errors: List[str] = field(default_factory=list)
```

含义：

- `blocked=True`：阻止后续执行。
- `block_reason`：阻止原因。
- `updated_output`：改写工具输出。
- `errors`：hook 异常、超时或解析失败。

---

## HookManager 做什么

`hooks/hook_manager.py` 是 hook 调度器。

它负责：

1. 维护普通 hook 队列和 final hook 队列。
2. 按事件名运行 hook。
3. 按 `matcher` 过滤工具名。
4. 合并 `HookResult`。
5. 把 `updated_output` 写回 `HookContext`。
6. 执行外部命令 hook。
7. 捕获 hook 异常和超时，避免主循环直接崩掉。

注册普通 hook：

```python
self.register("PreToolUse", builtin_hooks.log_pre_tool_use)
```

注册 final hook：

```python
self.register("PreToolUse", builtin_hooks.permission_check_hook, final=True)
```

两者不会冲突。普通 hook 进入 `callbacks`，final hook 进入 `final_callbacks`。

`PreToolUse` 的执行顺序是：

```text
普通 Python hook
-> 配置命令 hook
-> final Python hook
```

所以普通 hook 可以先记录或阻止执行，最后由权限 hook 检查工具参数。

---

## 内置 Hook

`hooks/builtin_hooks.py` 当前包含：

```python
log_session_start
log_before_model_call
log_after_model_call
log_pre_tool_use
permission_check_hook
log_post_tool_use
```

其中最重要的是 `permission_check_hook()`：

```python
def permission_check_hook(context: HookContext):
    permission = check_permission(context.tool_name or "", context.tool_input)
    if permission.allowed:
        return None

    reason = f"Permission denied: {permission.reason}"
    return HookResult(blocked=True, block_reason=reason)
```

这就是 s03 权限系统在 s04 中的接入方式。权限检查不再由 `dispatcher.py` 直接调用，而是作为 final `PreToolUse` hook 运行。

---

## Dispatcher 中的工具 Hook

`handlers/dispatcher.py` 的核心顺序：

```text
解析 tool_call
查找 handler
构造 HookContext
运行 PreToolUse hook
如果 blocked，直接返回
执行真实工具
运行 PostToolUse hook
如果 updated_output，使用新输出
返回工具结果
```

关键点：

- `PreToolUse` 阻止时，不执行真实工具。
- 权限拒绝时，返回 `Permission denied: ...`。
- `PostToolUse` 只在真实工具执行成功后运行。
- hook 消息会被拼到工具结果前，返回给模型。

---

## Agent Loop 中的生命周期 Hook

`agent_loop.py` 触发这些事件：

```text
main()
  -> SessionStart

每轮循环
  -> BeforeModelCall
  -> 模型调用
  -> AfterModelCall

没有工具调用时
  -> Stop
  -> 返回最终答案
```

当前生命周期 hook 主要用于日志观察。hook 返回文本只记录日志，不注入对话，避免破坏 OpenAI tool call 和 tool result 的顺序。

---

## 外部命令 Hook 配置

当前 `configs/hooks_config.yml` 默认是：

```yaml
enabled: false
timeout_seconds: 30

trust:
  require_marker: false
  marker_path: ".mini_claude_code_trusted"

events: {}
```

也就是说，当前只运行 Python 内置 hook，不运行外部命令 hook。

如果需要启用外部命令 hook，可以改成：

```yaml
enabled: true
timeout_seconds: 30

trust:
  require_marker: false
  marker_path: ".mini_claude_code_trusted"

events:
  PreToolUse:
    - name: "tool_log"
      matcher: "*"
      enabled: true
      command: "python hooks/log_tool_hook.py"
```

外部命令 hook 可以读取环境变量：

```text
HOOK_EVENT
HOOK_TOOL_NAME
HOOK_TOOL_INPUT
HOOK_TOOL_OUTPUT
```

退出码约定：

| 退出码 | 含义 |
|--------|------|
| `0` | 通过；stdout 如果是 JSON，可提供 `updatedOutput`；`message` / `additionalContext` 只记录日志 |
| `1` | 阻止执行；stderr 作为阻止原因 |
| `2` | 不阻止执行；stderr 作为附加消息 |

---

## 权限和 Hook 的关系

s04 后，权限检查已经是 hook，但它不是普通 hook，而是 final `PreToolUse` hook。

这保证了：

- PreToolUse hook 不会改写工具参数。
- 工具参数必须经过 `permission_check_hook()`。
- 普通 hook 不能绕过 `permission_config.yml` 的 deny 规则。
- 危险 bash 命令仍会被拒绝。
- 权限拒绝时，不执行真实工具，也不运行 `PostToolUse`。

---

## 可以验证的行为

### 1. 安全 bash 正常执行

```python
dispatch_tool_call({
    "function": {
        "name": "bash",
        "arguments": "{\"command\": \"Write-Output ok\"}"
    }
})
```

会看到：

```text
[hook:PreToolUse] 工具执行前
[hook:PreToolUse] 权限通过
[hook:PostToolUse] 工具执行后
```

### 2. 删除命令被权限 hook 拒绝

```text
cmd /c del /f /q summary.txt
```

结果：

```text
Permission denied: dangerous command keyword: del
```

### 3. Python 删除也会被拒绝

```text
python -c "import os; os.remove('data/summary.txt')"
```

结果：

```text
Permission denied: dangerous command keyword: os.remove
```

---

## 相对 s03 的变化

| 位置 | s03 | s04 |
|------|-----|-----|
| 权限检查 | dispatcher 直接调用 `check_permission()` | final `PreToolUse` hook 调用 `check_permission()` |
| 工具前日志 | dispatcher 普通日志 | `log_pre_tool_use()` |
| 工具后日志 | dispatcher 普通日志 | `log_post_tool_use()` |
| 扩展方式 | 继续改 dispatcher 或 agent loop | 注册 hook |
| 外部扩展 | 无 | 可通过 `hooks_config.yml` 启用命令 hook |

---

## 当前完成标准

- `SessionStart`、`BeforeModelCall`、`AfterModelCall`、`PreToolUse`、`PostToolUse`、`Stop` 事件已存在。
- Python 内置日志 hook 已注册。
- s03 权限检查已包装成 final `PreToolUse` hook。
- 工具执行前可以阻止执行，但不会改写参数。
- 工具执行后可以改写输出。
- 外部命令 hook 已支持，但默认关闭。
- hook 异常不会直接杀掉主循环。

---

## 下一步

s04 让扩展逻辑挂到了循环外。后续 s05 会加入 `TodoWrite`，让 Agent 在执行复杂任务前先维护一个短期计划。
