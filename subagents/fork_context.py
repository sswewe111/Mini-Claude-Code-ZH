from typing import Any, Dict, List

from utils.normalize_messages import normalize_messages


def _message_to_text(message: Dict[str, Any], max_chars: int) -> str:
    role = message.get("role", "unknown")
    content = str(message.get("content") or "").strip()
    if not content:
        return ""
    if len(content) > max_chars:
        content = content[:max_chars] + "\n...[已截断]"
    return f"{role}: {content}"


def summarize_parent_context(
    parent_messages: List[Dict[str, Any]],
    max_chars: int,
    include_tool_results: bool = False,
) -> str:
    """用规则方式生成父上下文摘要，避免把大量工具噪声带进子 Agent。"""
    if not parent_messages:
        return "父 Agent 没有可继承的历史上下文。"

    chunks = []
    remaining = max_chars
    for message in parent_messages:
        if message.get("role") == "tool" and not include_tool_results:
            continue
        text = _message_to_text(message, min(1200, remaining))
        if not text:
            continue
        if len(text) > remaining:
            text = text[:remaining] + "\n...[父上下文达到长度上限]"
        chunks.append(text)
        remaining -= len(text)
        if remaining <= 0:
            break

    if not chunks:
        return "父 Agent 历史中没有可继承的文本上下文。"
    return "\n\n".join(chunks)


def build_fork_messages(
    parent_messages: List[Dict[str, Any]],
    description: str,
    expected_output: str,
    config: Dict[str, Any],
) -> List[Dict[str, str]]:
    max_messages = int(config.get("FORK_CONTEXT_MAX_MESSAGES", 12))
    max_chars = int(config.get("FORK_CONTEXT_MAX_CHARS", 12000))
    include_tool_results = bool(config.get("FORK_INCLUDE_TOOL_RESULTS", False))
    recent_messages = parent_messages[-max_messages:]
    context_summary = summarize_parent_context(
        recent_messages,
        max_chars,
        include_tool_results=include_tool_results,
    )

    task_text = [
        "以下是父 Agent 当前上下文快照。它只用于帮助你理解背景，不代表你可以扩展任务范围。",
        context_summary,
        "当前子任务：",
        description,
    ]
    if expected_output:
        task_text.extend(["期望输出：", expected_output])

    return normalize_messages([
        {
            "role": "user",
            "content": "\n\n".join(task_text),
        }
    ])
