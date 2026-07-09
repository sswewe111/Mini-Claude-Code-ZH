from typing import Any, Dict, List, Optional

from handlers.dispatcher import _get_tool_name_and_args
from handlers.subagent_handlers import SUBAGENT_HANDLERS
from managers.compact_manager import COMPACT_MANAGER
from managers.memory_manager import MEMORY_MANAGER
from managers.recovery_manager import RecoveryManager
from managers.system_prompt_builder import build_subagent_system_prompt
from prompts.subagent_prompts import FORK_SUBAGENT_BOILERPLATE
from state.agent_state import LoopState, ToolRuntimeContext
from state.hook_state import HookContext
from tools_configs.subagent_configs import SUBAGENT_AVAILABLE_TOOLS
from utils.config_handler import compact_config, subagent_config
from utils.logger_handler import logger
from utils.normalize_messages import normalize_messages


def _assistant_to_message(message) -> dict:
    record = {
        "role": "assistant",
        "content": message.content or "",
    }
    if message.tool_calls:
        record["tool_calls"] = [
            tool_call.model_dump() if hasattr(tool_call, "model_dump") else tool_call
            for tool_call in message.tool_calls
        ]
    return record


def _get_tool_name(tool_call) -> str:
    if isinstance(tool_call, dict):
        return tool_call.get("function", {}).get("name", "")
    return tool_call.function.name


def _filter_tools(tool_names: List[str]) -> List[Dict[str, Any]]:
    allowed = set(tool_names)
    filtered = []
    for tool in SUBAGENT_AVAILABLE_TOOLS:
        name = tool.get("function", {}).get("name")
        if name in allowed:
            filtered.append(tool)
    return filtered


def _dispatch_subagent_tool_call(tool_call, hook_manager, runtime_context) -> str:
    try:
        name, args = _get_tool_name_and_args(tool_call)
    except Exception as exc:
        logger.exception("[subagent] 解析 tool_call 失败")
        return f"Error: invalid subagent tool call: {exc}"

    if runtime_context.allowed_tools and name not in runtime_context.allowed_tools:
        logger.warning("[subagent] 工具被子 Agent 允许列表拒绝: %s", name)
        return f"Error: subagent cannot use tool {name}"

    handler = SUBAGENT_HANDLERS.get(name)
    if not handler:
        logger.error("[subagent] 未知工具: %s", name)
        return f"Error: unknown subagent tool {name}"

    logger.info("[subagent] 准备执行工具: %s", name)
    pre_context = HookContext(
        event="PreToolUse",
        tool_name=name,
        tool_input=args,
        metadata={"tool_call_id": getattr(tool_call, "id", "")},
    )
    pre_result = hook_manager.run_hooks("PreToolUse", pre_context)
    if pre_result.blocked:
        reason = pre_result.block_reason or "blocked by hook"
        return reason if reason.startswith("Permission denied:") else f"Tool blocked by hook: {reason}"

    try:
        result = handler(args)
    except Exception as exc:
        logger.exception("[subagent] 工具执行异常: %s", name)
        return f"Error while running subagent tool {name}: {exc}"

    post_context = HookContext(
        event="PostToolUse",
        tool_name=name,
        tool_input=args,
        tool_output=result,
        metadata={"tool_call_id": getattr(tool_call, "id", "")},
    )
    post_result = hook_manager.run_hooks("PostToolUse", post_context)
    if post_result.updated_output is not None:
        return post_result.updated_output
    return result


def _initial_messages(
    description: str,
    expected_output: str,
    mode: str,
    runtime_context: ToolRuntimeContext,
    config: Dict[str, Any],
) -> List[dict]:
    if mode == "fork":
        from subagents.fork_context import build_fork_messages
        logger.info("[subagent] task 工具 fork 模式，构建子 Agent 消息上下文")
        parent_messages = runtime_context.parent_messages if runtime_context else []
        messages = build_fork_messages(parent_messages, description, expected_output, config)
        messages.insert(0, {"role": "user", "content": FORK_SUBAGENT_BOILERPLATE})
        return messages

    content = description
    if expected_output:
        content = f"{description}\n\n期望输出：\n{expected_output}"
    return [{"role": "user", "content": content}]


def _clip_result(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n...[子 Agent 结果过长，已截断]"


def _resolve_mode(config: Dict[str, Any]) -> str:
    mode = config.get("SUBAGENT_MODE", "non_fork")
    if mode not in ("non_fork", "fork"):
        logger.warning("[subagent] 未知 SUBAGENT_MODE: %s，回退到 non_fork", mode)
        return "non_fork"
    return mode


def _runtime_error(message: str) -> str:
    logger.error("[subagent] %s", message)
    return f"Subagent error: {message}"


def _max_output_tokens() -> int:
    return int(compact_config.get("MAX_OUTPUT_TOKENS", 2048))


def run_task_subagent(
    description: str,
    expected_output: str = "",
    runtime_context: Optional[ToolRuntimeContext] = None,
) -> str:
    """运行一次同步子 Agent，只返回最终 assistant 文本。"""
    if not runtime_context:
        return _runtime_error("task 工具缺少 runtime_context，无法启动子 Agent")
    if runtime_context.subagent_depth > 0:
        return _runtime_error("子 Agent 内禁止继续创建子 Agent")

    active_config = subagent_config
    active_mode = _resolve_mode(active_config)
    allowed_tools = list(active_config.get("ALLOWED_SUBAGENT_TOOLS", []))
    tools = _filter_tools(allowed_tools)
    if not tools:
        return _runtime_error("子 Agent 没有可用工具")

    max_turns = int(active_config.get("MAX_SUBAGENT_TURNS", 20))
    max_result_chars = int(active_config.get("SUBAGENT_RESULT_MAX_CHARS", 6000))
    workdir = runtime_context.workdir
    messages = _initial_messages(
        description=description,
        expected_output=expected_output,
        mode=active_mode,
        runtime_context=runtime_context,
        config=active_config,
    )
    state = LoopState(messages=messages)
    recovery_manager = RecoveryManager()
    child_context = ToolRuntimeContext(
        parent_messages=state.messages,
        client=runtime_context.client,
        model_id=runtime_context.model_id,
        hook_manager=runtime_context.hook_manager,
        workdir=runtime_context.workdir,
        subagent_depth=runtime_context.subagent_depth + 1,
        allowed_tools=allowed_tools,
        compact_manager=COMPACT_MANAGER,
        memory_manager=MEMORY_MANAGER,
    )


    for _ in range(max_turns):
        state.turn_count += 1
        logger.info("[subagent] 开始第 %s 轮循环", state.turn_count)
        active_model_id = recovery_manager.state.current_model_id or runtime_context.model_id
        runtime_context.hook_manager.run_hooks(
            "BeforeModelCall",
            HookContext(
                event="BeforeModelCall",
                messages=state.messages,
                model_id=active_model_id,
                metadata={
                    "turn_count": state.turn_count,
                    "client": runtime_context.client,
                    "compact_manager": COMPACT_MANAGER,
                    "memory_manager": MEMORY_MANAGER,
                    "subagent_depth": child_context.subagent_depth,
                    "allow_subagent_llm_compact": compact_config.get("ENABLE_SUBAGENT_LLM_COMPACT", False),
                },
            ),
        )

        def build_messages():
            return normalize_messages([
                {
                    "role": "system",
                    "content": build_subagent_system_prompt(workdir),
                },
                *state.messages,
            ])

        response = recovery_manager.create_chat_completion(
            client=runtime_context.client,
            model_id=runtime_context.model_id,
            build_messages=build_messages,
            tools=tools,
            tool_choice="auto",
            max_tokens=_max_output_tokens(),
            compact_manager=COMPACT_MANAGER,
            state_messages=state.messages,
        )
        assistant_message = response.choices[0].message
        state.messages.append(_assistant_to_message(assistant_message))

        continuation_message = recovery_manager.build_continuation_message(response.choices[0].finish_reason)
        if continuation_message:
            state.messages.append(continuation_message)
            continue

        tool_calls = assistant_message.tool_calls or []
        if not tool_calls:
            result = assistant_message.content or ""
            # logger.info("[subagent] 完成: turns=%s, result_length=%s", state.turn_count, len(result))
            return _clip_result(result, max_result_chars)

        for tool_call in tool_calls:
            tool_name = _get_tool_name(tool_call)
            if tool_name not in allowed_tools:
                result = f"Error: subagent cannot use tool {tool_name}"
            else:
                result = _dispatch_subagent_tool_call(
                    tool_call,
                    hook_manager=runtime_context.hook_manager,
                    runtime_context=child_context,
                )
            state.messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })

    message = f"子 Agent 超过最大轮数 {max_turns}，已停止"
    logger.warning("[subagent] %s", message)
    return message
