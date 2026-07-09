import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from managers.autonomous_manager import AUTONOMOUS_MANAGER
from managers.team_protocol_manager import TEAM_PROTOCOL_MANAGER
from state.team_state import TeamMemberRecord, TeamMessage
from tools.message_bus import MessageBus
from utils.config_handler import team_config
from utils.logger_handler import logger


class TeamManager:
    """管理 Agent Teams 的成员、线程和消息投递。"""

    def __init__(self):
        self.config = team_config
        self.bus = MessageBus(
            team_dir=self.config.get("TEAM_DIR", ".team"),
            inbox_dir=self.config.get("TEAM_INBOX_DIR", ".team/inbox"),
        )
        self.client = None
        self.model_id = ""
        self.hook_manager = None
        self.workdir = str(Path.cwd())
        self._members: Dict[str, TeamMemberRecord] = {}
        self._threads: Dict[str, threading.Thread] = {}
        self._lock = threading.RLock()
        self.protocol_manager = TEAM_PROTOCOL_MANAGER

    def configure_from_config(self) -> None:
        self.bus.configure(
            team_dir=self.config.get("TEAM_DIR", ".team"),
            inbox_dir=self.config.get("TEAM_INBOX_DIR", ".team/inbox"),
        )

    def ensure_store(self) -> None:
        self.configure_from_config()
        self.bus.ensure_store()
        self.protocol_manager.ensure_store()
        AUTONOMOUS_MANAGER.ensure_store()
        self._load_members()

    def start(self, client, model_id: str, hook_manager=None, workdir: str = "") -> None:
        self.client = client
        self.model_id = model_id
        self.hook_manager = hook_manager
        self.workdir = workdir or str(Path.cwd())
        self.ensure_store()
        logger.info("[team] Agent Teams 已初始化")

    def spawn(self, name: str, role: str, prompt: str) -> str:
        if not self.config.get("ENABLE_AGENT_TEAMS", True):
            return "Agent Teams 未启用。"
        if not self.client or not self.model_id:
            return "Agent Teams 尚未初始化，无法启动 teammate。"
        clean_name = self._normalize_member_name(name)
        if not clean_name:
            return "teammate 名称不能为空，只能包含字母、数字、下划线和短横线。"
        with self._lock:
            self._load_members()
            if clean_name == self.lead_name:
                return "不能使用 lead 作为 teammate 名称。"
            existing = self._members.get(clean_name)
            if existing and existing.status in ("starting", "running", "idle"):
                return f"teammate {clean_name} 已存在，当前状态: {existing.status}"
            active_count = sum(1 for item in self._members.values() if item.status in ("starting", "running", "idle"))
            if active_count >= int(self.config.get("MAX_TEAMMATES", 5)):
                return f"teammate 数量已达到上限: {active_count}"

            now = self._now()
            record = TeamMemberRecord(
                name=clean_name,
                role=role,
                prompt=prompt,
                status="starting",
                thread_name=f"teammate-{clean_name}",
                created_at=existing.created_at if existing else now,
                updated_at=now,
                last_seen_at=now,
                turn_count=0,
            )
            self._members[clean_name] = record
            self._save_members()

            thread = threading.Thread(
                target=self._run_teammate_thread,
                name=record.thread_name or f"teammate-{clean_name}",
                args=(record,),
                daemon=True,
            )
            self._threads[clean_name] = thread
            thread.start()
            self.bus.append_event("teammate_spawned", record.to_dict())
        return f"已启动 teammate {clean_name}（role={role}）。"

    def list_all(self) -> str:
        self.ensure_store()
        if not self._members:
            return "当前没有 teammate。"
        lines = ["当前团队成员："]
        for member in sorted(self._members.values(), key=lambda item: item.name):
            lines.append(
                f"- {member.name}: role={member.role}, status={member.status}, "
                f"turns={member.turn_count}, last_seen={member.last_seen_at or '-'}"
            )
        return "\n".join(lines)

    def member_names(self, include_inactive: bool = False) -> List[str]:
        self.ensure_store()
        names = []
        for name, member in self._members.items():
            if include_inactive or member.status in ("starting", "running", "idle"):
                names.append(name)
        return sorted(names)

    def send_message(self, to: str, content: str, msg_type: str = "message", sender: Optional[str] = None) -> str:
        sender = sender or self.lead_name
        message = self.bus.send(
            sender=sender,
            recipient=to,
            content=content,
            msg_type=msg_type or "message",
        )
        return f"已发送消息 {message.id}: {sender} -> {to} ({message.type})"

    def send_structured_message(
        self,
        sender: str,
        to: str,
        content: str,
        msg_type: str,
        metadata: Optional[dict] = None,
    ) -> TeamMessage:
        return self.bus.send(
            sender=sender,
            recipient=to,
            content=content,
            msg_type=msg_type,
            metadata=metadata or {},
        )

    def broadcast(self, content: str, recipients: Optional[Iterable[str]] = None, sender: Optional[str] = None) -> str:
        sender = sender or self.lead_name
        targets = list(recipients or self.member_names())
        if not targets:
            return "没有可广播的 teammate。"
        messages = self.bus.broadcast(sender=sender, recipients=targets, content=content)
        return f"已广播给 {len(messages)} 个 teammate: {', '.join(targets)}"

    def check_inbox(self, agent: Optional[str] = None, consume: bool = True) -> str:
        name = agent or self.lead_name
        messages = self.consume_inbox_messages(name=name, consume=consume)
        if not messages:
            return f"{name} 的 inbox 为空。"
        return self.format_messages(messages)

    def drain_lead_inbox_for_prompt(self) -> str:
        if not self.config.get("ENABLE_AGENT_TEAMS", True):
            return ""
        messages = self.consume_inbox_messages(name=self.lead_name, consume=True)
        if not messages:
            return ""
        return "<team_inbox>\n" + self.format_messages(messages) + "\n</team_inbox>"

    def consume_inbox_messages(self, name: str, consume: bool = True) -> List[TeamMessage]:
        messages = self.bus.read_inbox(
            name,
            consume=consume,
            limit=int(self.config.get("MAX_INBOX_MESSAGES_PER_TURN", 20)),
        )
        if consume and name == self.lead_name:
            self.route_protocol_messages(messages, recipient=name)
        return messages

    def route_protocol_messages(self, messages: List[TeamMessage], recipient: str) -> None:
        if not self.config.get("ENABLE_TEAM_PROTOCOLS", True):
            return
        for message in messages:
            if message.type in {
                "shutdown_approved",
                "shutdown_rejected",
                "plan_approval_approved",
                "plan_approval_rejected",
            }:
                record = self.protocol_manager.match_response(message)
                self.bus.append_event(
                    "protocol_response_matched" if record else "protocol_response_unmatched",
                    {
                        "recipient": recipient,
                        "message_id": message.id,
                        "message_type": message.type,
                        "request_id": message.metadata.get("request_id"),
                        "status": record.status if record else "",
                    },
                )
            elif message.type == "teammate_terminated":
                self.record_member_status(message.sender, "stopped")
                self.bus.append_event("teammate_terminated", message.to_dict())

    def request_shutdown(self, name: str, reason: str = "") -> str:
        if not self.config.get("ENABLE_TEAM_PROTOCOLS", True):
            return "Team Protocols 未启用。"
        self.ensure_store()
        clean_name = self._normalize_member_name(name)
        member = self._members.get(clean_name)
        if not member:
            return f"未找到 teammate: {clean_name}"
        if member.status in ("stopped", "failed"):
            return f"teammate {clean_name} 当前状态为 {member.status}，无需请求关闭。"
        record = self.protocol_manager.create_request(
            protocol="shutdown",
            sender=self.lead_name,
            recipient=clean_name,
            request_type="shutdown_request",
            payload={"reason": reason},
        )
        self.bus.send(
            sender=self.lead_name,
            recipient=clean_name,
            content=reason or "Lead 请求你完成当前收尾后体面关闭。",
            msg_type="shutdown_request",
            metadata={"request_id": record.request_id, "protocol": "shutdown", "reason": reason},
        )
        self.bus.append_event("shutdown_requested", record.to_dict())
        return f"已请求 teammate {clean_name} 关闭，request_id={record.request_id}"

    def submit_plan(
        self,
        sender: str,
        plan: str,
        risk_level: str = "",
        target_files: Optional[List[str]] = None,
    ) -> str:
        if not self.config.get("ENABLE_TEAM_PROTOCOLS", True):
            return "Team Protocols 未启用。"
        max_chars = int(self.config.get("PLAN_APPROVAL_MAX_CHARS", 6000))
        clipped_plan = plan[:max_chars]
        record = self.protocol_manager.create_request(
            protocol="plan_approval",
            sender=sender,
            recipient=self.lead_name,
            request_type="plan_approval_request",
            payload={
                "plan": clipped_plan,
                "risk_level": risk_level,
                "target_files": target_files or [],
            },
        )
        self.bus.send(
            sender=sender,
            recipient=self.lead_name,
            content=clipped_plan,
            msg_type="plan_approval_request",
            metadata={
                "request_id": record.request_id,
                "protocol": "plan_approval",
                "risk_level": risk_level,
                "target_files": target_files or [],
            },
        )
        self.bus.append_event("plan_approval_requested", record.to_dict())
        return f"已提交计划审批，request_id={record.request_id}，请等待 Lead 审批。"

    def review_plan(self, request_id: str, approve: bool, feedback: str = "") -> str:
        record = self.protocol_manager.get_request(request_id)
        if not record:
            return f"未找到计划审批请求: {request_id}"
        if record.protocol != "plan_approval":
            return f"请求 {request_id} 不是计划审批请求，而是 {record.protocol}"
        if record.status != "pending":
            return f"请求 {request_id} 已处理，当前状态: {record.status}"
        response_type = "plan_approval_approved" if approve else "plan_approval_rejected"
        resolved = self.protocol_manager.resolve_request(
            request_id=request_id,
            response_type=response_type,
            response={"feedback": feedback, "approve": approve},
        )
        self.bus.send(
            sender=self.lead_name,
            recipient=record.sender,
            content=feedback or ("计划已批准。" if approve else "计划已拒绝。"),
            msg_type=response_type,
            metadata={
                "request_id": request_id,
                "protocol": "plan_approval",
                "approve": approve,
                "feedback": feedback,
            },
        )
        self.bus.append_event("plan_approval_reviewed", resolved.to_dict() if resolved else {"request_id": request_id})
        return f"已{'批准' if approve else '拒绝'}计划 {request_id}，已通知 {record.sender}。"

    def protocol_status(self, request_id: str = "", include_resolved: bool = True) -> str:
        return self.protocol_manager.format_requests(
            request_id=request_id,
            include_resolved=include_resolved,
        )

    def record_member_status(
        self,
        name: str,
        status: str,
        turn_count: Optional[int] = None,
        error: Optional[str] = None,
    ) -> None:
        with self._lock:
            self._load_members()
            member = self._members.get(name)
            now = self._now()
            if not member:
                return
            member.status = status
            member.updated_at = now
            member.last_seen_at = now
            if turn_count is not None:
                member.turn_count = turn_count
            if error:
                member.metadata["error"] = error
            self._save_members()

    def send_from_teammate(self, sender: str, to: str, content: str, msg_type: str = "message") -> str:
        return self.send_message(to=to, content=content, msg_type=msg_type, sender=sender)

    @property
    def lead_name(self) -> str:
        return str(self.config.get("LEAD_AGENT_NAME", "lead"))

    @staticmethod
    def format_messages(messages: List[TeamMessage]) -> str:
        lines = []
        for message in messages:
            lines.append(f"From {message.sender} [{message.type}]: {message.content}")
        return "\n".join(lines)

    def _run_teammate_thread(self, record: TeamMemberRecord) -> None:
        from subagents.teammate_agent import run_teammate_agent

        try:
            self.record_member_status(record.name, "running")
            run_teammate_agent(
                member=record,
                client=self.client,
                model_id=self.model_id,
                hook_manager=self.hook_manager,
                workdir=self.workdir,
                team_manager=self,
            )
        except Exception as exc:
            logger.exception("[team] teammate 线程异常: %s", record.name)
            self.record_member_status(record.name, "failed", error=str(exc))
            self.bus.send(
                sender=record.name,
                recipient=self.lead_name,
                content=f"teammate {record.name} 执行失败: {exc}",
                msg_type="error",
            )

    def _load_members(self) -> None:
        self.bus.ensure_store()
        try:
            data = json.loads(self.bus.members_file.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError:
            data = {"members": []}
        members = {}
        for item in data.get("members", []):
            if not isinstance(item, dict):
                continue
            record = TeamMemberRecord.from_dict(item)
            if record.name:
                members[record.name] = record
        self._members = members

    def _save_members(self) -> None:
        self.bus.ensure_store()
        payload = {
            "team_id": self.config.get("TEAM_ID", "default"),
            "lead": self.lead_name,
            "updated_at": self._now(),
            "members": [member.to_dict() for member in sorted(self._members.values(), key=lambda item: item.name)],
        }
        self.bus.members_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def _normalize_member_name(name: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", (name or "").strip())
        return cleaned.strip("_-").lower()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


TEAM_MANAGER = TeamManager()
