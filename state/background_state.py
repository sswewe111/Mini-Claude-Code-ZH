from dataclasses import asdict, dataclass, field
from typing import Dict, Optional


BACKGROUND_STATUSES = {"running", "completed", "failed", "cancelled"}


@dataclass
class BackgroundTaskRecord:
    """后台命令任务的持久状态。"""

    id: str
    command: str
    status: str = "running"
    exit_code: Optional[int] = None
    output_path: str = ""
    owner: str = "main"
    started_at: str = ""
    finished_at: str = ""
    summary: str = ""
    metadata: Dict = field(default_factory=dict)
    notified: bool = False

    @classmethod
    def from_dict(cls, data: Dict) -> "BackgroundTaskRecord":
        return cls(
            id=str(data.get("id", "")).strip(),
            command=str(data.get("command", "")),
            status=str(data.get("status", "running")).strip(),
            exit_code=data.get("exit_code"),
            output_path=str(data.get("output_path", "")),
            owner=str(data.get("owner", "main") or "main"),
            started_at=str(data.get("started_at", "")),
            finished_at=str(data.get("finished_at", "")),
            summary=str(data.get("summary", "")),
            metadata=dict(data.get("metadata") or {}),
            notified=bool(data.get("notified", False)),
        )

    def to_dict(self) -> Dict:
        return asdict(self)
