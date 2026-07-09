import json
from typing import Any


def estimate_text_tokens(text: str) -> int:
    """粗略估算 token 数；第一版避免引入额外 tokenizer 依赖。"""
    if not text:
        return 0
    # 中文通常接近 1 字 1 token，英文大致 4 字 1 token；这里取保守估算。
    return max(1, len(text) // 2)


def estimate_message_tokens(messages: list) -> int:
    """按序列化后的消息粗估上下文 token。"""
    try:
        text = json.dumps(messages, ensure_ascii=False)
    except TypeError:
        text = str(messages)
    return estimate_text_tokens(text)


def text_size(value: Any) -> int:
    """统一计算消息内容长度。"""
    if value is None:
        return 0
    if isinstance(value, str):
        return len(value)
    try:
        return len(json.dumps(value, ensure_ascii=False))
    except TypeError:
        return len(str(value))
