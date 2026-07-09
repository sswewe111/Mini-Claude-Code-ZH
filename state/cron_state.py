from dataclasses import asdict, dataclass, field
from typing import Dict


@dataclass
class CronJobRecord:
    """定时任务定义。"""

    id: str
    cron: str
    prompt: str
    recurring: bool = True
    durable: bool = True
    enabled: bool = True
    created_at: str = ""
    updated_at: str = ""
    last_fired_at: str = ""
    last_fire_marker: str = ""
    fire_count: int = 0
    metadata: Dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict) -> "CronJobRecord":
        return cls(
            id=str(data.get("id", "")).strip(),
            cron=str(data.get("cron", "")).strip(),
            prompt=str(data.get("prompt", "")),
            recurring=bool(data.get("recurring", True)),
            durable=bool(data.get("durable", True)),
            enabled=bool(data.get("enabled", True)),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
            last_fired_at=str(data.get("last_fired_at", "")),
            last_fire_marker=str(data.get("last_fire_marker", "")),
            fire_count=int(data.get("fire_count", 0) or 0),
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class FiredCronEvent:
    """已经触发、等待交付给 Agent 的定时工作事件。"""

    event_id: str
    job_id: str
    cron: str
    prompt: str
    fired_at: str
    durable: bool
    recurring: bool

    def to_dict(self) -> Dict:
        return asdict(self)
