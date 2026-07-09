ALLOWED_KEYS = {"role", "content", "tool_calls", "tool_call_id", "name"}


def normalize_messages(messages: list) -> list:
    """保留 OpenAI Chat Completions 接口需要的字段，剥离内部临时字段。"""
    normalized = []
    for message in messages:
        if not message:
            continue
        clean = {key: value for key, value in message.items() if key in ALLOWED_KEYS}
        if clean.get("role") == "assistant" and "tool_calls" in clean:
            clean["content"] = clean.get("content") or ""
        normalized.append(clean)
    return normalized
