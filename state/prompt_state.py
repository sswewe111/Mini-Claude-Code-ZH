from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class PromptSection:
    """System prompt 中的一个可组合段落。"""

    name: str
    content: str
    dynamic: bool = False


@dataclass
class SystemPromptContext:
    """组装 system prompt 所需的运行时状态。"""

    workdir: str
    agent_type: str = "main"
    enabled_tools: List[str] = field(default_factory=list)
    skill_catalog: str = ""
    memory_index: str = ""
    project_instructions: str = ""
    runtime_context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PromptBuildResult:
    """Prompt builder 的结构化输出，方便调试 section 和缓存。"""

    text: str
    section_names: List[str] = field(default_factory=list)
    cache_hit: bool = False
