from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class MemoryItem:
    """单条长期记忆的轻量元数据。"""

    name: str
    description: str
    type: str
    scope: str
    path: Path
    updated_at: str = ""


@dataclass
class MemorySelection:
    """本轮被召回的记忆列表。"""

    items: List[MemoryItem] = field(default_factory=list)
    reason: str = ""
    source: str = "keyword"


@dataclass
class MemoryState:
    """Memory 运行时状态；持久内容仍以 .memory/ 文件为准。"""

    loaded_index_text: str = ""
    loaded_memory_paths: List[str] = field(default_factory=list)
    last_dream_at: str = ""
    saved_this_turn: bool = False
