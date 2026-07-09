from dataclasses import dataclass, field
from typing import Dict


@dataclass
class WorktreeRecord:
    """A git worktree registered for an isolated task workspace."""

    name: str
    path: str
    branch: str
    base_ref: str = "HEAD"
    task_id: str = ""
    status: str = "active"
    created_at: str = ""
    updated_at: str = ""
    metadata: Dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "WorktreeRecord":
        return cls(
            name=str(data.get("name", "")),
            path=str(data.get("path", "")),
            branch=str(data.get("branch", "")),
            base_ref=str(data.get("base_ref", "HEAD")),
            task_id=str(data.get("task_id", "")),
            status=str(data.get("status", "active")),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "path": self.path,
            "branch": self.branch,
            "base_ref": self.base_ref,
            "task_id": self.task_id,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }
