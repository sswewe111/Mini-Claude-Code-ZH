from dataclasses import dataclass
from typing import Optional

from state.task_state import TaskRecord


@dataclass
class AutonomousClaimResult:
    """teammate 自动认领任务的一次尝试结果。"""

    claimed: bool
    message: str
    task: Optional[TaskRecord] = None
