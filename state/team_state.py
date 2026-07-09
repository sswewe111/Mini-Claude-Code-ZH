from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional


@dataclass
class TeamMessage:
    """团队消息总线中的一条结构化消息。"""

    id: str
    sender: str
    recipient: str
    type: str
    content: str
    created_at: str
    correlation_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TeamMessage":
        return cls(
            id=str(data.get("id", "")),
            sender=str(data.get("sender", "")),
            recipient=str(data.get("recipient", "")),
            type=str(data.get("type", "message")),
            content=str(data.get("content", "")),
            created_at=str(data.get("created_at", "")),
            correlation_id=data.get("correlation_id"),
            metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else {},
        )


@dataclass
class TeamMemberRecord:
    """团队成员注册表中的一条记录。"""

    name: str
    role: str
    prompt: str
    status: str
    thread_name: Optional[str]
    created_at: str
    updated_at: str
    last_seen_at: Optional[str] = None
    turn_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TeamMemberRecord":
        return cls(
            name=str(data.get("name", "")),
            role=str(data.get("role", "")),
            prompt=str(data.get("prompt", "")),
            status=str(data.get("status", "unknown")),
            thread_name=data.get("thread_name"),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
            last_seen_at=data.get("last_seen_at"),
            turn_count=int(data.get("turn_count", 0) or 0),
            metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else {},
        )
