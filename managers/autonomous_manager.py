import json
from datetime import datetime
from typing import List

from managers.task_manager import TASK_MANAGER
from state.autonomous_state import AutonomousClaimResult
from state.task_state import TaskRecord
from utils.config_handler import team_config
from utils.path_sandbox import safe_path


class AutonomousManager:
    """空闲 teammate 的任务扫描和自动认领。"""

    def __init__(self):
        self.config = team_config
        self.event_file = safe_path(self.config.get("AUTONOMOUS_EVENT_FILE", ".team/autonomous_events.jsonl"))

    def ensure_store(self) -> None:
        self.event_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.event_file.exists():
            self.event_file.touch()

    def scan_ready_tasks(self, teammate_name: str, role: str = "") -> List[TaskRecord]:
        TASK_MANAGER.ensure_store()
        tasks = TASK_MANAGER.ready_unowned_tasks()
        if self.config.get("AUTONOMOUS_REQUIRE_TASK_METADATA_MATCH", False):
            key = str(self.config.get("AUTONOMOUS_ROLE_METADATA_KEY", "role"))
            role_lower = str(role or "").lower()
            tasks = [
                task for task in tasks
                if not task.metadata.get(key) or str(task.metadata.get(key)).lower() in role_lower
            ]
        self.append_event("scan", teammate_name, {"ready_count": len(tasks)})
        return tasks

    def try_claim_next(self, teammate_name: str, role: str = "") -> AutonomousClaimResult:
        if not self.config.get("ENABLE_AUTONOMOUS_AGENTS", True):
            return AutonomousClaimResult(False, "Autonomous Agents 未启用。")
        if not self.config.get("AUTONOMOUS_TASK_SCAN_ENABLED", True):
            return AutonomousClaimResult(False, "Autonomous task scan 未启用。")

        tasks = self.scan_ready_tasks(teammate_name=teammate_name, role=role)
        if not tasks:
            return AutonomousClaimResult(False, "没有可自动认领的 ready task。")

        for task in tasks[: int(self.config.get("AUTONOMOUS_MAX_CLAIMS_PER_IDLE", 1))]:
            result = TASK_MANAGER.claim(task.id, owner=teammate_name)
            if result.startswith("已认领"):
                claimed_task = TASK_MANAGER.load_task(task.id)
                self.append_event("claim_success", teammate_name, {"task_id": task.id, "message": result})
                return AutonomousClaimResult(True, result, claimed_task)
            self.append_event("claim_failed", teammate_name, {"task_id": task.id, "message": result})
        return AutonomousClaimResult(False, "扫描到任务，但认领失败。")

    def format_claimed_task(self, task: TaskRecord, teammate_name: str) -> str:
        return (
            "<claimed_task>\n"
            f"id: {task.id}\n"
            f"subject: {task.subject}\n"
            f"owner: {task.owner or teammate_name}\n"
            f"blocked_by: {', '.join(task.blocked_by) if task.blocked_by else '-'}\n"
            "description:\n"
            f"{task.description or '(无描述)'}\n\n"
            f"你已成功认领该任务。完成后必须调用 task_complete(task_id=\"{task.id}\", "
            f"owner=\"{teammate_name}\", summary=\"...\")，然后用 team_send_message 向 lead 汇报。\n"
            "</claimed_task>"
        )

    def append_event(self, event_type: str, teammate_name: str, payload: dict) -> None:
        self.ensure_store()
        record = {
            "type": event_type,
            "teammate": teammate_name,
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "payload": payload,
        }
        with self.event_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


AUTONOMOUS_MANAGER = AutonomousManager()
