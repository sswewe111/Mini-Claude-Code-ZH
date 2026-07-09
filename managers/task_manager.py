import json
import os
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from state.task_state import TASK_STATUSES, TaskRecord
from utils.config_handler import task_config
from utils.logger_handler import logger
from utils.path_sandbox import safe_path


class TaskManager:
    """文件持久化任务图管理器。"""

    def __init__(self, config: Optional[Dict] = None) -> None:
        self.config = config or task_config
        self.root = safe_path(str(self.config.get("TASK_DIR", ".tasks")))
        self.tasks_dir = self.root / "tasks"
        self.locks_dir = self.root / "locks"
        self.index_path = self.root / "index.json"
        self.events_path = self.root / "events.jsonl"
        self.id_prefix = str(self.config.get("TASK_ID_PREFIX", "task_"))

    def ensure_store(self) -> None:
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.locks_dir.mkdir(parents=True, exist_ok=True)
        if not self.index_path.exists():
            self._write_json(self.index_path, {
                "version": 1,
                "next_id": 1,
                "tasks_dir": "tasks",
                "updated_at": self._now(),
            })
        if not self.events_path.exists():
            self.events_path.touch()

    def create(
        self,
        subject: str,
        description: str = "",
        blocked_by: Optional[List[str]] = None,
        metadata: Optional[Dict] = None,
    ) -> str:
        self.ensure_store()
        subject = str(subject or "").strip()
        if not subject:
            raise ValueError("task subject 不能为空")

        dep_ids = self._normalize_ids(blocked_by or [])
        self._ensure_dependencies_exist(dep_ids)
        task_id = self._next_task_id()
        now = self._now()
        task = TaskRecord(
            id=task_id,
            subject=subject,
            description=str(description or ""),
            blocked_by=dep_ids,
            metadata=dict(metadata or {}),
            created_at=now,
            updated_at=now,
        )
        self._save_task(task)
        self._rebuild_blocks()
        self.append_event("create", task_id, {"blocked_by": dep_ids})
        return self.render_task(task)

    def get(self, task_id: str) -> str:
        task = self.load_task(task_id)
        return json.dumps(task.to_dict(), ensure_ascii=False, indent=2)

    def list_all(
        self,
        include_completed: bool = True,
        owner: Optional[str] = None,
        status: Optional[str] = None,
    ) -> str:
        self.ensure_store()
        tasks = self._sorted_tasks(self._load_all_tasks())
        if owner:
            tasks = [task for task in tasks if task.owner == owner]
        if status:
            tasks = [task for task in tasks if task.status == status]
        if not include_completed:
            tasks = [task for task in tasks if task.status not in {"completed", "cancelled"}]

        max_items = int(self.config.get("MAX_TASKS_IN_LIST_OUTPUT", 50))
        visible = tasks[:max_items]
        if not visible:
            return "当前没有匹配的持久任务。"

        lines = [f"任务看板：{len(visible)}/{len(tasks)}"]
        for task in visible:
            readiness = self._readiness_label(task)
            owner_text = task.owner or "-"
            deps = ",".join(task.blocked_by) if task.blocked_by else "-"
            lines.append(
                f"- {task.id} [{task.status}/{readiness}] owner={owner_text} "
                f"deps={deps} :: {task.subject}"
            )
        if len(tasks) > len(visible):
            lines.append(f"... 还有 {len(tasks) - len(visible)} 个任务未显示")
        return "\n".join(lines)

    def update(self, task_id: str, **changes) -> str:
        task = self.load_task(task_id)
        if "subject" in changes and changes["subject"] is not None:
            subject = str(changes["subject"]).strip()
            if not subject:
                raise ValueError("task subject 不能为空")
            task.subject = subject
        if "description" in changes and changes["description"] is not None:
            task.description = str(changes["description"])
        if "active_form" in changes and changes["active_form"] is not None:
            task.active_form = str(changes["active_form"])
        if "metadata" in changes and changes["metadata"] is not None:
            if not isinstance(changes["metadata"], dict):
                raise ValueError("metadata 必须是对象")
            task.metadata.update(changes["metadata"])
        if "blocked_by" in changes and changes["blocked_by"] is not None:
            dep_ids = self._normalize_ids(changes["blocked_by"])
            self._ensure_dependencies_exist(dep_ids)
            if task.id in dep_ids:
                raise ValueError("任务不能依赖自己")
            if self.config.get("ENABLE_CYCLE_DETECTION", True):
                self._ensure_no_cycle(task.id, dep_ids)
            task.blocked_by = dep_ids
        if "status" in changes and changes["status"] is not None:
            self._set_status(task, str(changes["status"]))
        if "owner" in changes:
            owner = changes["owner"]
            task.owner = str(owner).strip() if owner else None
        task.updated_at = self._now()
        self._save_task(task)
        self._rebuild_blocks()
        self.append_event("update", task.id, {"changes": self._event_changes(changes)})
        return self.render_task(self.load_task(task.id))

    def can_start(self, task_id: str) -> bool:
        task = self.load_task(task_id)
        return self._can_start_task(task)

    def ready_unowned_tasks(self) -> List[TaskRecord]:
        """返回可以开始且尚未被认领的 pending 任务。"""
        self.ensure_store()
        tasks = self._sorted_tasks(self._load_all_tasks())
        return [
            task for task in tasks
            if task.status == "pending" and not task.owner and self._can_start_task(task)
        ]

    def claim(self, task_id: str, owner: str = "main") -> str:
        owner = str(owner or "").strip() or "main"
        with self._task_lock(task_id):
            task = self.load_task(task_id)
            if task.status != "pending":
                return f"无法认领 {task.id}：当前状态是 {task.status}。"
            if task.owner:
                return f"无法认领 {task.id}：已被 {task.owner} 认领。"
            missing_or_open = self._blocking_dependencies(task)
            if missing_or_open:
                return f"无法认领 {task.id}：依赖未完成 {missing_or_open}。"
            task.owner = owner
            task.status = "in_progress"
            task.updated_at = self._now()
            self._save_task(task)
            self.append_event("claim", task.id, {"owner": owner})
            return f"已认领 {task.id}：{task.subject}，owner={owner}"

    def complete(self, task_id: str, owner: Optional[str] = None, summary: str = "") -> str:
        with self._task_lock(task_id):
            task = self.load_task(task_id)
            if task.status != "in_progress":
                return f"无法完成 {task.id}：当前状态是 {task.status}，只有 in_progress 可完成。"
            if self.config.get("REQUIRE_OWNER_TO_COMPLETE", True):
                owner_value = str(owner or "").strip()
                if task.owner and owner_value and task.owner != owner_value:
                    return f"无法完成 {task.id}：owner 不匹配，当前 owner={task.owner}。"
            task.status = "completed"
            if summary:
                task.metadata["completion_summary"] = str(summary)
            task.updated_at = self._now()
            self._save_task(task)
            unblocked = [t.id for t in self._load_all_tasks() if t.status == "pending" and self._can_start_task(t)]
            self.append_event("complete", task.id, {"owner": task.owner, "unblocked": unblocked})

        message = f"已完成 {task.id}：{task.subject}"
        if unblocked:
            message += "\n刚刚可开始的任务：" + ", ".join(unblocked)
        return message

    def cancel(self, task_id: str, reason: str = "") -> str:
        task = self.load_task(task_id)
        if task.status == "completed":
            return f"无法取消 {task.id}：任务已完成。"
        task.status = "cancelled"
        task.owner = None
        if reason:
            task.metadata["cancel_reason"] = str(reason)
        task.updated_at = self._now()
        self._save_task(task)
        self.append_event("cancel", task.id, {"reason": reason})
        return f"已取消 {task.id}：{task.subject}"

    def append_event(self, event: str, task_id: str, payload: Optional[Dict] = None) -> None:
        self.ensure_store()
        record = {"time": self._now(), "event": event, "task_id": task_id}
        if payload:
            record.update(payload)
        with self.events_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    def render_task(self, task: TaskRecord) -> str:
        readiness = self._readiness_label(task)
        return "\n".join([
            f"{task.id} [{task.status}/{readiness}] {task.subject}",
            f"owner: {task.owner or '-'}",
            f"blocked_by: {', '.join(task.blocked_by) if task.blocked_by else '-'}",
            f"blocks: {', '.join(task.blocks) if task.blocks else '-'}",
        ])

    def load_task(self, task_id: str) -> TaskRecord:
        self.ensure_store()
        path = self._task_path(task_id)
        if not path.exists():
            raise ValueError(f"任务不存在: {task_id}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"任务文件损坏: {path}") from exc
        task = TaskRecord.from_dict(data)
        self._validate_task(task)
        return task

    def _task_path(self, task_id: str) -> Path:
        task_id = str(task_id or "").strip()
        if not task_id or "/" in task_id or "\\" in task_id or ".." in task_id:
            raise ValueError(f"非法任务 ID: {task_id}")
        return self.tasks_dir / f"{task_id}.json"

    def _load_all_tasks(self) -> List[TaskRecord]:
        self.ensure_store()
        tasks: List[TaskRecord] = []
        for path in sorted(self.tasks_dir.glob("*.json")):
            try:
                tasks.append(TaskRecord.from_dict(json.loads(path.read_text(encoding="utf-8"))))
            except json.JSONDecodeError as exc:
                raise ValueError(f"任务文件损坏: {path}") from exc
        for task in tasks:
            self._validate_task(task)
        return tasks

    def _save_task(self, task: TaskRecord) -> None:
        self._validate_task(task)
        self._write_json(self._task_path(task.id), task.to_dict())

    def _write_json(self, path: Path, data: Dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp_path, path)

    def _next_task_id(self) -> str:
        with self._named_lock("index"):
            index = self._read_index()
            next_id = int(index.get("next_id", 1))
            task_id = f"{self.id_prefix}{next_id:06d}"
            index["next_id"] = next_id + 1
            index["updated_at"] = self._now()
            self._write_json(self.index_path, index)
            return task_id

    def _read_index(self) -> Dict:
        self.ensure_store()
        try:
            return json.loads(self.index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"任务索引损坏: {self.index_path}") from exc

    def _validate_task(self, task: TaskRecord) -> None:
        if not task.id:
            raise ValueError("任务缺少 id")
        if not task.subject:
            raise ValueError(f"任务 {task.id} 缺少 subject")
        if task.status not in TASK_STATUSES:
            raise ValueError(f"任务 {task.id} 状态非法: {task.status}")

    def _normalize_ids(self, ids: List[str]) -> List[str]:
        if not isinstance(ids, list):
            raise ValueError("blocked_by 必须是列表")
        normalized: List[str] = []
        for raw_id in ids:
            task_id = str(raw_id or "").strip()
            if not task_id:
                continue
            self._task_path(task_id)
            if task_id not in normalized:
                normalized.append(task_id)
        return normalized

    def _ensure_dependencies_exist(self, dep_ids: List[str]) -> None:
        missing = [dep_id for dep_id in dep_ids if not self._task_path(dep_id).exists()]
        if missing:
            raise ValueError(f"依赖任务不存在: {missing}")

    def _blocking_dependencies(self, task: TaskRecord) -> List[str]:
        blocking: List[str] = []
        for dep_id in task.blocked_by:
            path = self._task_path(dep_id)
            if not path.exists():
                blocking.append(dep_id)
                continue
            dep = self.load_task(dep_id)
            if dep.status != "completed":
                blocking.append(dep_id)
        return blocking

    def _can_start_task(self, task: TaskRecord) -> bool:
        return not self._blocking_dependencies(task)

    def _readiness_label(self, task: TaskRecord) -> str:
        if task.status == "pending":
            return "ready" if self._can_start_task(task) else "blocked"
        return "closed" if task.status in {"completed", "cancelled"} else "claimed"

    def _sorted_tasks(self, tasks: List[TaskRecord]) -> List[TaskRecord]:
        def rank(task: TaskRecord):
            if task.status == "in_progress" and task.owner:
                group = 0
            elif task.status == "pending" and self._can_start_task(task):
                group = 1
            elif task.status == "pending":
                group = 2
            elif task.status == "completed":
                group = 3
            else:
                group = 4
            return group, task.id

        return sorted(tasks, key=rank)

    def _rebuild_blocks(self) -> None:
        tasks = self._load_all_tasks()
        by_id = {task.id: task for task in tasks}
        for task in tasks:
            task.blocks = []
        for task in tasks:
            for dep_id in task.blocked_by:
                if dep_id in by_id and task.id not in by_id[dep_id].blocks:
                    by_id[dep_id].blocks.append(task.id)
        for task in tasks:
            task.blocks = sorted(task.blocks)
            self._save_task(task)

    def _ensure_no_cycle(self, task_id: str, new_blocked_by: List[str]) -> None:
        graph = {task.id: list(task.blocked_by) for task in self._load_all_tasks()}
        graph[task_id] = list(new_blocked_by)

        visiting = set()
        visited = set()

        def visit(node: str) -> bool:
            if node in visiting:
                return True
            if node in visited:
                return False
            visiting.add(node)
            for dep in graph.get(node, []):
                if visit(dep):
                    return True
            visiting.remove(node)
            visited.add(node)
            return False

        if visit(task_id):
            raise ValueError("依赖更新会形成环，已拒绝")

    def _set_status(self, task: TaskRecord, status: str) -> None:
        if status not in TASK_STATUSES:
            raise ValueError(f"非法任务状态: {status}")
        task.status = status
        if status in {"pending", "cancelled"}:
            task.owner = None

    def _event_changes(self, changes: Dict) -> Dict:
        safe = {}
        for key, value in changes.items():
            if value is not None:
                safe[key] = value
        return safe

    @contextmanager
    def _task_lock(self, task_id: str):
        with self._named_lock(task_id):
            yield

    @contextmanager
    def _named_lock(self, name: str):
        if not self.config.get("ENABLE_TASK_LOCKS", True):
            yield
            return
        self.ensure_store()
        lock_name = str(name or "").replace("/", "_").replace("\\", "_")
        lock_path = self.locks_dir / f"{lock_name}.lock"
        timeout = float(self.config.get("LOCK_TIMEOUT_SECONDS", 5))
        start = time.time()
        fh = None
        while True:
            try:
                fh = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fh, str(os.getpid()).encode("utf-8"))
                break
            except FileExistsError:
                if time.time() - start >= timeout:
                    raise TimeoutError(f"获取任务锁超时: {name}")
                time.sleep(0.05)
        try:
            yield
        finally:
            if fh is not None:
                os.close(fh)
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass

    def _now(self) -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")


TASK_MANAGER = TaskManager()
