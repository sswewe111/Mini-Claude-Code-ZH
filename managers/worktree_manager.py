import json
import os
import re
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from managers.task_manager import TASK_MANAGER
from state.worktree_state import WorktreeRecord
from utils.config_handler import worktree_config
from utils.path_sandbox import WORKDIR, safe_path, safe_path_under


class WorktreeManager:
    """Manage task-bound git worktrees without changing process cwd."""

    def __init__(self):
        self.config = worktree_config
        self.root = safe_path(self.config.get("WORKTREE_ROOT", ".worktrees"))
        self.index_file = safe_path(self.config.get("WORKTREE_INDEX_FILE", ".worktrees/index.json"))
        self.event_file = safe_path(self.config.get("WORKTREE_EVENT_FILE", ".worktrees/events.jsonl"))
        self._lock = threading.RLock()

    def ensure_store(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_file.parent.mkdir(parents=True, exist_ok=True)
        self.event_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.index_file.exists():
            self._write_index({"worktrees": []})
        if not self.event_file.exists():
            self.event_file.write_text("", encoding="utf-8")

    def create(self, name: str, task_id: str = "", base_ref: str = "") -> str:
        if not self.config.get("ENABLE_WORKTREE_ISOLATION", True):
            return "Worktree Isolation 未启用。"
        self.ensure_store()
        clean_name = self._validate_name(name)
        base_ref = str(base_ref or self.config.get("WORKTREE_BASE_REF", "HEAD")).strip() or "HEAD"
        branch = f"{self.config.get('WORKTREE_BRANCH_PREFIX', 'wt/')}{clean_name}"
        path = safe_path_under(self.root, clean_name)

        with self._lock:
            records = self._load_records()
            existing = records.get(clean_name)
            if existing and existing.status != "removed":
                return f"worktree {clean_name} 已存在，状态为 {existing.status}。"
            if path.exists():
                return f"worktree 路径已存在: {self._display_path(path)}"

            ok, output = self._git(["rev-parse", "--show-toplevel"])
            if not ok:
                return "当前工作区不是 git 仓库，无法创建 worktree。"

            if not self.config.get("WORKTREE_ALLOW_CREATE_WITH_DIRTY_REPO", False):
                dirty = self._git_output(["status", "--porcelain"])
                if dirty.strip():
                    return "主工作区存在未提交改动，配置禁止创建 worktree。"

            ok, output = self._git(["worktree", "add", "-b", branch, str(path), base_ref])
            if not ok:
                self._append_event("git_error", clean_name, {"operation": "create", "output": output})
                return f"创建 worktree 失败:\n{output}"

            now = self._now()
            record = WorktreeRecord(
                name=clean_name,
                path=str(path),
                branch=branch,
                base_ref=base_ref,
                task_id=str(task_id or ""),
                status="active",
                created_at=now,
                updated_at=now,
            )
            records[clean_name] = record
            self._save_records(records)
            self._append_event("create", clean_name, record.to_dict())

        bind_text = ""
        if task_id:
            bind_text = "\n" + self.bind_task(task_id=task_id, name=clean_name)
        return (
            f"已创建 worktree {clean_name}\n"
            f"path: {self._display_path(path)}\n"
            f"branch: {branch}"
            f"{bind_text}"
        )

    def bind_task(self, task_id: str, name: str) -> str:
        self.ensure_store()
        clean_name = self._validate_name(name)
        task_id = str(task_id or "").strip()
        if not task_id:
            return "task_id 不能为空。"
        TASK_MANAGER.load_task(task_id)

        with self._lock:
            records = self._load_records()
            record = records.get(clean_name)
            if not record or record.status == "removed":
                return f"未找到 active worktree: {clean_name}"
            record.task_id = task_id
            record.updated_at = self._now()
            records[clean_name] = record
            self._save_records(records)

        metadata_key = str(self.config.get("WORKTREE_BIND_METADATA_KEY", "worktree"))
        metadata = {
            metadata_key: {
                "name": record.name,
                "path": self._display_path(Path(record.path)),
                "branch": record.branch,
            }
        }
        TASK_MANAGER.update(task_id, metadata=metadata)
        self._append_event("bind_task", clean_name, {"task_id": task_id, "metadata": metadata[metadata_key]})
        return f"已绑定 task {task_id} -> worktree {clean_name} ({record.branch})"

    def list_all(self, include_removed: bool = False) -> str:
        self.ensure_store()
        records = sorted(self._load_records().values(), key=lambda item: item.name)
        if not include_removed:
            records = [record for record in records if record.status != "removed"]
        if not records:
            return "当前没有 worktree 记录。"
        lines = ["当前 worktree："]
        for record in records:
            lines.append(
                f"- {record.name}: status={record.status}, task={record.task_id or '-'}, "
                f"branch={record.branch}, path={self._display_path(Path(record.path))}"
            )
        return "\n".join(lines)

    def status(self, name: str) -> str:
        record = self._get_record(name)
        path = Path(record.path)
        ok, output = self._git(["-C", str(path), "status", "--short", "--branch"])
        if not ok:
            return f"获取 worktree 状态失败:\n{output}"
        return (
            f"worktree: {record.name}\n"
            f"status: {record.status}\n"
            f"task_id: {record.task_id or '-'}\n"
            f"branch: {record.branch}\n"
            f"path: {self._display_path(path)}\n\n"
            f"{output.strip() or '(clean)'}"
        )

    def keep(self, name: str, reason: str = "") -> str:
        record = self._set_status(name, "kept", {"reason": reason}, event_type="keep")
        return (
            f"已保留 worktree {record.name} 用于 review。\n"
            f"path: {self._display_path(Path(record.path))}\n"
            f"branch: {record.branch}"
        )

    def remove(self, name: str, discard_changes: bool = False) -> str:
        record = self._get_record(name)
        path = Path(record.path)
        if self.config.get("WORKTREE_REMOVE_REQUIRES_CLEAN", True) and not discard_changes:
            dirty = self._git_output(["-C", str(path), "status", "--porcelain"])
            if dirty.strip():
                self._append_event("remove_rejected", record.name, {"reason": "dirty", "status": dirty})
                return (
                    f"worktree {record.name} 存在未提交改动，已拒绝删除。\n"
                    "如确认丢弃，请再次调用 worktree_remove(discard_changes=true)。"
                )

        ok, output = self._git(["worktree", "remove", str(path), "--force"])
        if not ok:
            self._append_event("git_error", record.name, {"operation": "remove", "output": output})
            return f"删除 worktree 失败:\n{output}"

        branch_output = ""
        if record.branch:
            _, branch_output = self._git(["branch", "-D", record.branch])
        self._set_status(
            record.name,
            "removed",
            {"discard_changes": discard_changes, "branch_output": branch_output},
            event_type="remove",
        )
        return f"已删除 worktree {record.name}，分支 {record.branch} 已清理。"

    def get_for_task(self, task_id: str) -> Optional[WorktreeRecord]:
        if not self.config.get("ENABLE_WORKTREE_ISOLATION", True):
            return None
        try:
            task = TASK_MANAGER.load_task(task_id)
        except Exception:
            return None
        metadata_key = str(self.config.get("WORKTREE_BIND_METADATA_KEY", "worktree"))
        binding = task.metadata.get(metadata_key)
        if not isinstance(binding, dict):
            return None
        name = binding.get("name")
        if not name:
            return None
        try:
            record = self._get_record(str(name))
        except Exception:
            return None
        if record.status not in {"active", "kept"}:
            return None
        if not Path(record.path).exists():
            return None
        return record

    def resolve_task_workdir(self, task_id: str) -> Optional[str]:
        record = self.get_for_task(task_id)
        if not record:
            return None
        return str(Path(record.path).resolve())

    def format_worktree_context(self, task_id: str) -> str:
        record = self.get_for_task(task_id)
        if not record:
            return ""
        return (
            "\nworktree:\n"
            f"name: {record.name}\n"
            f"path: {self._display_path(Path(record.path))}\n"
            f"branch: {record.branch}\n"
            "你的文件和命令工具会在该隔离目录中执行。\n"
        )

    def record_auto_enter(self, teammate_name: str, task_id: str, workdir: str) -> None:
        self._append_event(
            "auto_enter",
            Path(workdir).name,
            {"teammate": teammate_name, "task_id": task_id, "workdir": self._display_path(Path(workdir))},
        )

    def _get_record(self, name: str) -> WorktreeRecord:
        clean_name = self._validate_name(name)
        self.ensure_store()
        record = self._load_records().get(clean_name)
        if not record:
            raise ValueError(f"未找到 worktree: {clean_name}")
        return record

    def _set_status(
        self,
        name: str,
        status: str,
        metadata: Optional[dict] = None,
        event_type: Optional[str] = None,
    ) -> WorktreeRecord:
        clean_name = self._validate_name(name)
        with self._lock:
            records = self._load_records()
            record = records.get(clean_name)
            if not record:
                raise ValueError(f"未找到 worktree: {clean_name}")
            record.status = status
            record.updated_at = self._now()
            if metadata:
                record.metadata.update(metadata)
            records[clean_name] = record
            self._save_records(records)
        self._append_event(event_type or status, clean_name, {"metadata": metadata or {}})
        return record

    def _validate_name(self, name: str) -> str:
        clean = str(name or "").strip()
        if clean in {"", ".", ".."}:
            raise ValueError("worktree name 不能为空或特殊路径。")
        if "/" in clean or "\\" in clean:
            raise ValueError("worktree name 不能包含路径分隔符。")
        pattern = str(self.config.get("WORKTREE_NAME_PATTERN", r"^[A-Za-z0-9._-]{1,64}$"))
        if not re.fullmatch(pattern, clean):
            raise ValueError(f"worktree name 不合法: {clean}")
        return clean

    def _load_records(self) -> Dict[str, WorktreeRecord]:
        self.ensure_store()
        try:
            data = json.loads(self.index_file.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError:
            data = {"worktrees": []}
        records = {}
        for item in data.get("worktrees", []):
            if isinstance(item, dict):
                record = WorktreeRecord.from_dict(item)
                if record.name:
                    records[record.name] = record
        return records

    def _save_records(self, records: Dict[str, WorktreeRecord]) -> None:
        payload = {"worktrees": [record.to_dict() for record in sorted(records.values(), key=lambda item: item.name)]}
        self._write_index(payload)

    def _write_index(self, payload: dict) -> None:
        self.index_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.index_file.with_suffix(self.index_file.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp_path, self.index_file)

    def _append_event(self, event_type: str, name: str, payload: dict) -> None:
        self.ensure_store()
        event = {
            "type": event_type,
            "worktree": name,
            "created_at": self._now(),
            "payload": payload,
        }
        with self.event_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")

    def _git(self, args: List[str], cwd: Optional[Path] = None) -> Tuple[bool, str]:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=str(cwd or WORKDIR),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, str(exc)
        output = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
        return result.returncode == 0, output

    def _git_output(self, args: List[str]) -> str:
        _, output = self._git(args)
        return output

    @staticmethod
    def _display_path(path: Path) -> str:
        resolved = path.resolve()
        try:
            return str(resolved.relative_to(WORKDIR))
        except ValueError:
            return str(resolved)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


WORKTREE_MANAGER = WorktreeManager()
