from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


TASK_STATUSES = {"pending", "in_progress", "completed", "cancelled"}


@dataclass
class TaskRecord:
    """持久任务图中的一个任务节点。"""

    id: str
    subject: str
    description: str = ""
    status: str = "pending"
    owner: Optional[str] = None
    active_form: str = ""
    blocked_by: List[str] = field(default_factory=list)
    blocks: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_dict(cls, data: Dict) -> "TaskRecord":
        return cls(
            id=str(data.get("id", "")).strip(),
            subject=str(data.get("subject", "")).strip(),
            description=str(data.get("description", "")),
            status=str(data.get("status", "pending")).strip(),
            owner=data.get("owner"),
            active_form=str(data.get("active_form") or data.get("activeForm") or ""),
            blocked_by=list(data.get("blocked_by") or data.get("blockedBy") or []),
            blocks=list(data.get("blocks") or []),
            metadata=dict(data.get("metadata") or {}),
            created_at=str(data.get("created_at") or data.get("createdAt") or ""),
            updated_at=str(data.get("updated_at") or data.get("updatedAt") or ""),
        )

    def to_dict(self) -> Dict:
        return asdict(self)
