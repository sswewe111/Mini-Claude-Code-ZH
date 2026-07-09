from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class HookContext:
    """Hook 运行时上下文；不同事件只填自己需要的字段。"""

    event: str
    tool_name: Optional[str] = None
    tool_input: Dict[str, Any] = field(default_factory=dict)
    tool_output: Optional[str] = None
    messages: Optional[list] = None
    model_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HookResult:
    """Hook 的结构化返回值，避免用异常或散乱字符串控制主流程。"""

    blocked: bool = False
    block_reason: str = ""
    updated_output: Optional[str] = None
    errors: List[str] = field(default_factory=list)
