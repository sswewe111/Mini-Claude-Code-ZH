import json
import threading
from datetime import datetime, timezone
from typing import List, Optional

from state.team_protocol_state import ProtocolRequestRecord
from state.team_state import TeamMessage
from utils.config_handler import team_config
from utils.path_sandbox import safe_path


APPROVED_RESPONSE_TYPES = {
    "shutdown_approved",
    "plan_approval_approved",
}

REJECTED_RESPONSE_TYPES = {
    "shutdown_rejected",
    "plan_approval_rejected",
}

EXPECTED_RESPONSES = {
    "shutdown": {"shutdown_approved", "shutdown_rejected"},
    "plan_approval": {"plan_approval_approved", "plan_approval_rejected"},
}


class TeamProtocolManager:
    """维护 Team Protocols 的请求状态和响应匹配。"""

    def __init__(self):
        self.config = team_config
        self._lock = threading.RLock()

    @property
    def request_file(self):
        return safe_path(self.config.get("TEAM_REQUEST_FILE", ".team/requests.json"))

    def ensure_store(self) -> None:
        path = self.request_file
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text('{"requests": []}\n', encoding="utf-8")

    def create_request(
        self,
        protocol: str,
        sender: str,
        recipient: str,
        request_type: str,
        payload: Optional[dict] = None,
    ) -> ProtocolRequestRecord:
        with self._lock:
            records = self._load_records()
            now = self._now()
            record = ProtocolRequestRecord(
                request_id=self._next_request_id(records),
                protocol=protocol,
                sender=sender,
                recipient=recipient,
                status="pending",
                request_type=request_type,
                payload=payload or {},
                created_at=now,
                updated_at=now,
            )
            records.append(record)
            self._save_records(records)
            return record

    def resolve_request(
        self,
        request_id: str,
        response_type: str,
        response: Optional[dict] = None,
    ) -> Optional[ProtocolRequestRecord]:
        with self._lock:
            records = self._load_records()
            record = self._find(records, request_id)
            if not record or record.status != "pending":
                return record
            expected = EXPECTED_RESPONSES.get(record.protocol, set())
            if response_type not in expected:
                return record
            record.response_type = response_type
            record.response = response or {}
            record.status = "approved" if response_type in APPROVED_RESPONSE_TYPES else "rejected"
            record.updated_at = self._now()
            record.resolved_at = record.updated_at
            self._save_records(records)
            return record

    def match_response(self, message: TeamMessage) -> Optional[ProtocolRequestRecord]:
        request_id = str(message.metadata.get("request_id") or "")
        protocol = str(message.metadata.get("protocol") or "")
        if not request_id:
            return None
        with self._lock:
            records = self._load_records()
            record = self._find(records, request_id)
            if not record or record.status != "pending":
                return record
            if protocol and protocol != record.protocol:
                return record
            expected = EXPECTED_RESPONSES.get(record.protocol, set())
            if message.type not in expected:
                return record
            record.response_type = message.type
            record.response = {
                "sender": message.sender,
                "recipient": message.recipient,
                "content": message.content,
                "metadata": message.metadata,
            }
            record.status = "approved" if message.type in APPROVED_RESPONSE_TYPES else "rejected"
            record.updated_at = self._now()
            record.resolved_at = record.updated_at
            self._save_records(records)
            return record

    def get_request(self, request_id: str) -> Optional[ProtocolRequestRecord]:
        with self._lock:
            return self._find(self._load_records(), request_id)

    def list_requests(self, include_resolved: bool = True) -> List[ProtocolRequestRecord]:
        with self._lock:
            records = self._load_records()
        if include_resolved:
            return records
        return [record for record in records if record.status == "pending"]

    def format_requests(self, request_id: str = "", include_resolved: bool = True) -> str:
        if request_id:
            record = self.get_request(request_id)
            if not record:
                return f"未找到协议请求: {request_id}"
            records = [record]
        else:
            records = self.list_requests(include_resolved=include_resolved)
        if not records:
            return "当前没有协议请求。"
        lines = ["团队协议请求："]
        for record in records:
            lines.append(
                f"- {record.request_id}: protocol={record.protocol}, status={record.status}, "
                f"{record.sender}->{record.recipient}, request={record.request_type}, response={record.response_type or '-'}"
            )
        return "\n".join(lines)

    def _load_records(self) -> List[ProtocolRequestRecord]:
        self.ensure_store()
        try:
            data = json.loads(self.request_file.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError:
            data = {"requests": []}
        records = []
        for item in data.get("requests", []):
            if isinstance(item, dict):
                records.append(ProtocolRequestRecord.from_dict(item))
        return records

    def _save_records(self, records: List[ProtocolRequestRecord]) -> None:
        self.ensure_store()
        payload = {
            "updated_at": self._now(),
            "requests": [record.to_dict() for record in records],
        }
        self.request_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _next_request_id(self, records: List[ProtocolRequestRecord]) -> str:
        prefix = str(self.config.get("TEAM_REQUEST_ID_PREFIX", "team_req_"))
        max_number = 0
        for record in records:
            if record.request_id.startswith(prefix):
                suffix = record.request_id[len(prefix):]
                if suffix.isdigit():
                    max_number = max(max_number, int(suffix))
        return f"{prefix}{max_number + 1:06d}"

    @staticmethod
    def _find(records: List[ProtocolRequestRecord], request_id: str) -> Optional[ProtocolRequestRecord]:
        for record in records:
            if record.request_id == request_id:
                return record
        return None

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


TEAM_PROTOCOL_MANAGER = TeamProtocolManager()
