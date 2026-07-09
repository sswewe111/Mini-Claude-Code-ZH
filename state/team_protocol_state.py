from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ProtocolRequestRecord:
    """团队协议中的 request-response 状态记录。"""

    request_id: str
    protocol: str
    sender: str
    recipient: str
    status: str
    request_type: str
    response_type: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    response: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    resolved_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProtocolRequestRecord":
        return cls(
            request_id=str(data.get("request_id", "")),
            protocol=str(data.get("protocol", "")),
            sender=str(data.get("sender", "")),
            recipient=str(data.get("recipient", "")),
            status=str(data.get("status", "pending")),
            request_type=str(data.get("request_type", "")),
            response_type=str(data.get("response_type", "")),
            payload=data.get("payload") if isinstance(data.get("payload"), dict) else {},
            response=data.get("response") if isinstance(data.get("response"), dict) else {},
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
            resolved_at=data.get("resolved_at"),
        )
