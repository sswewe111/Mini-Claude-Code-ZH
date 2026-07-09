from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass
class LoopState:
    """保存一次 Agent 运行所需的最小状态。"""

    messages: list
    turn_count: int = 0


@dataclass
class PlanItem:
    """当前会话中的一个计划项。"""

    content: str
    status: str = "pending"
    active_form: str = ""


@dataclass
class PlanningState:
    """TodoWrite 的内存状态，只在当前进程内有效。"""

    items: List[PlanItem] = field(default_factory=list)
    rounds_since_update: int = 0


@dataclass
class ToolRuntimeContext:
    """工具执行时可选的运行时上下文，供 task 这类工具访问父 Agent 信息。"""

    parent_messages: list
    client: Any
    model_id: str
    hook_manager: Any
    workdir: str
    subagent_depth: int = 0
    allowed_tools: Optional[List[str]] = None
    compact_manager: Any = None
    memory_manager: Any = None
