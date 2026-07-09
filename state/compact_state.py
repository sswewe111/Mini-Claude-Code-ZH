from dataclasses import dataclass, field
from typing import Dict


@dataclass
class PersistedToolOutput:
    """记录一次被落盘的工具输出。"""

    tool_call_id: str
    path: str
    original_chars: int
    preview: str


@dataclass
class CompactState:
    """Context Compact 在当前进程内维护的轻量状态。"""

    has_compacted: bool = False
    last_summary: str = ""
    last_transcript_path: str = ""
    reactive_retries: int = 0
    compacted_tool_outputs: Dict[str, PersistedToolOutput] = field(default_factory=dict)
    pending_manual_focus: str = ""
