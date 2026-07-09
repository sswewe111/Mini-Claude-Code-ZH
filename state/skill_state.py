from dataclasses import dataclass
from pathlib import Path


@dataclass
class SkillManifest:
    """技能目录中的轻量元数据，不包含完整 SKILL.md 正文。"""

    name: str
    description: str
    path: Path
    entry_file: Path
