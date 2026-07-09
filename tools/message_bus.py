import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from state.team_state import TeamMessage
from utils.path_sandbox import safe_path


class MessageBus:
    """基于 jsonl 文件收件箱的轻量消息总线。"""

    def __init__(self, team_dir: str = ".team", inbox_dir: str = ".team/inbox"):
        self.team_dir = safe_path(team_dir)
        self.inbox_dir = safe_path(inbox_dir)
        self.members_file = self.team_dir / "members.json"
        self.events_file = self.team_dir / "events.jsonl"
        self.locks_dir = self.team_dir / "locks"
        self._global_lock = threading.RLock()
        self._inbox_locks: Dict[str, threading.RLock] = {}

    def configure(self, team_dir: str, inbox_dir: str) -> None:
        with self._global_lock:
            self.team_dir = safe_path(team_dir)
            self.inbox_dir = safe_path(inbox_dir)
            self.members_file = self.team_dir / "members.json"
            self.events_file = self.team_dir / "events.jsonl"
            self.locks_dir = self.team_dir / "locks"

    def ensure_store(self) -> None:
        self.team_dir.mkdir(parents=True, exist_ok=True)
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        self.locks_dir.mkdir(parents=True, exist_ok=True)
        if not self.members_file.exists():
            self.members_file.write_text('{"members": []}\n', encoding="utf-8")
        if not self.events_file.exists():
            self.events_file.write_text("", encoding="utf-8")

    def send(
        self,
        sender: str,
        recipient: str,
        content: str,
        msg_type: str = "message",
        metadata: Optional[dict] = None,
        correlation_id: Optional[str] = None,
    ) -> TeamMessage:
        self.ensure_store()
        message = TeamMessage(
            id=f"team_msg_{uuid.uuid4().hex[:12]}",
            sender=sender,
            recipient=recipient,
            type=msg_type or "message",
            content=content,
            created_at=self._now(),
            correlation_id=correlation_id,
            metadata=metadata or {},
        )
        inbox = self._inbox_path(recipient)
        with self._lock_for(recipient):
            with inbox.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(message.to_dict(), ensure_ascii=False) + "\n")
        self.append_event("message_sent", message.to_dict())
        return message

    def broadcast(
        self,
        sender: str,
        recipients: Iterable[str],
        content: str,
        msg_type: str = "message",
        metadata: Optional[dict] = None,
    ) -> List[TeamMessage]:
        messages = []
        for recipient in recipients:
            messages.append(
                self.send(
                    sender=sender,
                    recipient=recipient,
                    content=content,
                    msg_type=msg_type,
                    metadata=metadata,
                )
            )
        return messages

    def read_inbox(self, name: str, consume: bool = True, limit: Optional[int] = None) -> List[TeamMessage]:
        self.ensure_store()
        inbox = self._inbox_path(name)
        if not inbox.exists():
            return []
        with self._lock_for(name):
            lines = inbox.read_text(encoding="utf-8").splitlines()
            if not lines:
                return []
            selected = lines[:limit] if limit else lines
            remaining = lines[len(selected):] if limit else []
            messages = []
            for line in selected:
                if not line.strip():
                    continue
                try:
                    messages.append(TeamMessage.from_dict(json.loads(line)))
                except json.JSONDecodeError:
                    self.append_event("message_decode_error", {"recipient": name, "line": line[:500]})
            if consume:
                inbox.write_text("\n".join(remaining) + ("\n" if remaining else ""), encoding="utf-8")
        if messages:
            self.append_event("inbox_read", {"recipient": name, "count": len(messages), "consume": consume})
        return messages

    def append_event(self, event_type: str, payload: dict) -> None:
        self.ensure_store()
        event = {
            "type": event_type,
            "created_at": self._now(),
            "payload": payload,
        }
        with self._global_lock:
            with self.events_file.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")

    def _inbox_path(self, name: str) -> Path:
        safe_name = "".join(ch for ch in name if ch.isalnum() or ch in ("_", "-", ".")).strip(".")
        if not safe_name:
            safe_name = "unknown"
        return self.inbox_dir / f"{safe_name}.jsonl"

    def _lock_for(self, name: str) -> threading.RLock:
        with self._global_lock:
            if name not in self._inbox_locks:
                self._inbox_locks[name] = threading.RLock()
            return self._inbox_locks[name]

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
