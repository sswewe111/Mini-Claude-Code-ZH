import json
from typing import Tuple

from handlers.base_handlers import BASE_HANDLERS
from state.hook_state import HookContext
from utils.logger_handler import logger
from hooks.hook_manager import get_default_hook_manager


def _get_tool_name_and_args(tool_call) -> Tuple[str, dict]:
    """兼容 OpenAI SDK 对象和普通 dict 两种 tool_call 表示。"""
    if isinstance(tool_call, dict):
        function = tool_call.get("function", {})
        name = function.get("name")
        # OpenAI tool_call 的 arguments 来自模型生成的函数调用参数。
        # 在 Chat Completions 中它通常是 JSON 字符串，例如 '{"path": "README.md"}'。
        raw_args = function.get("arguments") or "{}"
    else:
        name = tool_call.function.name
        # SDK 对象格式同理：tool_call.function.arguments 是模型返回的 JSON 字符串。
        raw_args = tool_call.function.arguments or "{}"

    if isinstance(raw_args, str):
        try:
            args = json.loads(raw_args or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError(f"tool arguments is not valid JSON: {raw_args}") from exc
    else:
        args = raw_args
    return name, args


def _get_tool_call_id(tool_call) -> str:
    if isinstance(tool_call, dict):
        return tool_call.get("id", "")
    return getattr(tool_call, "id", "")


def dispatch_tool_call(tool_call, hook_manager=None, runtime_context=None) -> str:
    """根据工具名分发调用；这里不写具体工具逻辑。"""
    hook_manager = hook_manager or get_default_hook_manager()
    try:
        name, args = _get_tool_name_and_args(tool_call)
    except Exception as exc:
        logger.exception("解析 tool_call 失败")
        return f"Error: invalid tool call: {exc}"

    # logger.info("分发工具调用: %s", name)
    # logger.info("工具参数: %s", args)
    handler = BASE_HANDLERS.get(name)
    if not handler:
        logger.error("未知工具: %s", name)
        return f"Error: unknown tool {name}"

    pre_context = HookContext(
        event="PreToolUse",
        tool_name=name,
        tool_input=args,
        metadata={"tool_call_id": _get_tool_call_id(tool_call)},
    )
    pre_result = hook_manager.run_hooks("PreToolUse", pre_context)
    if pre_result.blocked:
        reason = pre_result.block_reason or "blocked by hook"
        logger.warning("PreToolUse Hook 阻止工具执行: %s, 原因: %s", name, reason)
        output = reason if reason.startswith("Permission denied:") else f"Tool blocked by hook: {reason}"
        return output
    try:
        if name == "task":
            result = handler(args, runtime_context=runtime_context)
        elif name in {
            "spawn_teammate",
            "team_send_message",
            "team_broadcast",
            "team_check_inbox",
            "team_list",
            "team_request_shutdown",
            "team_review_plan",
            "team_protocol_status",
        }:
            result = handler(args, runtime_context=runtime_context)
        else:
            result = handler(args)
        # logger.info("工具执行完成: %s", name)
        post_context = HookContext(
            event="PostToolUse",
            tool_name=name,
            tool_input=args,
            tool_output=result,
            metadata={"tool_call_id": _get_tool_call_id(tool_call)},
        )
        post_result = hook_manager.run_hooks("PostToolUse", post_context)
        if post_result.updated_output is not None:
            result = post_result.updated_output
            logger.info("PostToolUse Hook 更新工具输出: %s", name)
        return result
    except Exception as exc:
        logger.exception("工具执行异常: %s", name)
        return f"Error while running {name}: {exc}"
