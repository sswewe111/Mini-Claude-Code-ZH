import json
import os
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from state.background_state import BACKGROUND_STATUSES, BackgroundTaskRecord
from tools.bash_tools import _shell_command
from utils.config_handler import background_config
from utils.path_sandbox import safe_path


class BackgroundManager:
    """后台命令任务管理器。"""

    def __init__(self, config: Optional[Dict] = None) -> None:
        self.config = config or background_config
        self.root = safe_path(str(self.config.get("RUNTIME_TASK_DIR", ".runtime-tasks")))
        output_dir = str(self.config.get("OUTPUT_DIR", ".runtime-tasks/outputs"))
        self.outputs_dir = safe_path(output_dir)
        self.index_path = self.root / "index.json"
        self.events_path = self.root / "events.jsonl"
        self.id_prefix = str(self.config.get("TASK_ID_PREFIX", "bg_"))
        self.lock = threading.Lock()

    def ensure_store(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        if not self.index_path.exists():
            self._write_index({
                "version": 1,
                "next_id": 1,
                "tasks": {},
                "updated_at": self._now(),
            })
        if not self.events_path.exists():
            self.events_path.touch()

    def run_command(
        self,
        command: str,
        owner: str = "main",
        cwd: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> str:
        if not self.config.get("ENABLE_BACKGROUND_TASKS", True):
            raise ValueError("Background Tasks 未启用")

        command = str(command or "").strip()
        if not command:
            raise ValueError("后台命令不能为空")

        self.ensure_store()
        bg_id = self._next_id()
        output_path = self.outputs_dir / f"{bg_id}.txt"
        record = BackgroundTaskRecord(
            id=bg_id,
            command=command,
            owner=str(owner or "main"),
            output_path=str(output_path.relative_to(Path.cwd())),
            started_at=self._now(),
        )
        self._put_record(record)
        self.append_event("start", bg_id, {"command": command, "owner": record.owner})

        thread = threading.Thread(
            target=self._worker,
            args=(bg_id, command, cwd, timeout),
            daemon=True,
            name=f"background-{bg_id}",
        )
        thread.start()

        return "\n".join([
            f"后台任务已启动: {bg_id}",
            f"command: {command}",
            "status: running",
            f"output_path: {record.output_path}",
            "后续完成后会以 <task_notification> 注入。",
        ])

    def get(self, bg_id: str, tail_chars: int = 2000) -> str:
        record = self._get_record(bg_id)
        output_tail = self._read_output_tail(record.output_path, tail_chars)
        payload = record.to_dict()
        payload["output_tail"] = output_tail
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def list_all(self, include_completed: bool = True) -> str:
        self.ensure_store()
        records = self._sorted_records()
        if not include_completed:
            records = [r for r in records if r.status == "running"]
        max_items = int(self.config.get("MAX_BACKGROUND_TASKS_IN_LIST", 50))
        visible = records[:max_items]
        if not visible:
            return "当前没有匹配的后台任务。"

        lines = [f"后台任务：{len(visible)}/{len(records)}"]
        for record in visible:
            exit_text = "-" if record.exit_code is None else str(record.exit_code)
            lines.append(
                f"- {record.id} [{record.status}] exit={exit_text} "
                f"owner={record.owner} output={record.output_path} :: {record.command}"
            )
        if len(records) > len(visible):
            lines.append(f"... 还有 {len(records) - len(visible)} 个后台任务未显示")
        return "\n".join(lines)

    def drain_notifications(self) -> List[str]:
        self.ensure_store()
        notifications: List[str] = []
        with self.lock:
            index = self._read_index_unlocked()
            tasks = index.get("tasks", {})
            for bg_id, data in list(tasks.items()):
                record = BackgroundTaskRecord.from_dict(data)
                if record.status == "running" or record.notified:
                    continue
                notifications.append(self._format_notification(record))
                record.notified = True
                tasks[bg_id] = record.to_dict()
                self._append_event_unlocked("notify", bg_id, {"status": record.status})
            index["updated_at"] = self._now()
            self._write_index_unlocked(index)
        return notifications

    def append_event(self, event: str, bg_id: str, payload: Optional[Dict] = None) -> None:
        self.ensure_store()
        with self.lock:
            self._append_event_unlocked(event, bg_id, payload or {})

    def _worker(self, bg_id: str, command: str, cwd: Optional[str], timeout: Optional[int]) -> None:
        output_path = self.outputs_dir / f"{bg_id}.txt"
        shell_name, command_args = _shell_command(command)
        effective_cwd = safe_path(cwd) if cwd else Path.cwd()
        timeout_value = self._timeout(timeout)
        try:
            result = subprocess.run(
                command_args,
                shell=False,
                cwd=effective_cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_value,
            )
            stdout = result.stdout.strip()
            stderr = result.stderr.strip()
            output_text = self._format_output(shell_name, command, result.returncode, stdout, stderr)
            output_path.write_text(output_text, encoding="utf-8")
            status = "completed" if result.returncode == 0 else "failed"
            summary = self._summarize_text(output_text)
            self._finish_record(bg_id, status, result.returncode, summary)
        except subprocess.TimeoutExpired as exc:
            output_text = self._format_output(
                shell_name,
                command,
                None,
                (exc.stdout or "").strip() if isinstance(exc.stdout, str) else "",
                f"command timed out after {timeout_value} seconds",
            )
            output_path.write_text(output_text, encoding="utf-8")
            self._finish_record(bg_id, "failed", None, f"命令超时: {timeout_value}s")
        except Exception as exc:
            output_path.write_text(f"command: {command}\n\nerror:\n{exc}\n", encoding="utf-8")
            self._finish_record(bg_id, "failed", None, f"后台任务异常: {exc}")

    def _finish_record(self, bg_id: str, status: str, exit_code: Optional[int], summary: str) -> None:
        with self.lock:
            index = self._read_index_unlocked()
            tasks = index.get("tasks", {})
            if bg_id not in tasks:
                return
            record = BackgroundTaskRecord.from_dict(tasks[bg_id])
            record.status = status
            record.exit_code = exit_code
            record.finished_at = self._now()
            record.summary = summary
            tasks[bg_id] = record.to_dict()
            index["updated_at"] = self._now()
            self._write_index_unlocked(index)
            self._append_event_unlocked(status if status == "failed" else "complete", bg_id, {
                "exit_code": exit_code,
                "summary": summary,
            })

    def _put_record(self, record: BackgroundTaskRecord) -> None:
        if record.status not in BACKGROUND_STATUSES:
            raise ValueError(f"后台任务状态非法: {record.status}")
        with self.lock:
            index = self._read_index_unlocked()
            index.setdefault("tasks", {})[record.id] = record.to_dict()
            index["updated_at"] = self._now()
            self._write_index_unlocked(index)

    def _get_record(self, bg_id: str) -> BackgroundTaskRecord:
        bg_id = self._normalize_bg_id(bg_id)
        with self.lock:
            index = self._read_index_unlocked()
            data = index.get("tasks", {}).get(bg_id)
        if not data:
            raise ValueError(f"后台任务不存在: {bg_id}")
        return BackgroundTaskRecord.from_dict(data)

    def _sorted_records(self) -> List[BackgroundTaskRecord]:
        with self.lock:
            index = self._read_index_unlocked()
            records = [BackgroundTaskRecord.from_dict(data) for data in index.get("tasks", {}).values()]
        rank = {"running": 0, "failed": 1, "completed": 2, "cancelled": 3}
        return sorted(records, key=lambda record: (rank.get(record.status, 9), record.id))

    def _next_id(self) -> str:
        with self.lock:
            index = self._read_index_unlocked()
            next_id = int(index.get("next_id", 1))
            bg_id = f"{self.id_prefix}{next_id:06d}"
            index["next_id"] = next_id + 1
            index["updated_at"] = self._now()
            self._write_index_unlocked(index)
            return bg_id

    def _read_index(self) -> Dict:
        self.ensure_store()
        with self.lock:
            return self._read_index_unlocked()

    def _read_index_unlocked(self) -> Dict:
        try:
            return json.loads(self.index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"后台任务索引损坏: {self.index_path}") from exc

    def _write_index(self, data: Dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with self.lock:
            self._write_index_unlocked(data)

    def _write_index_unlocked(self, data: Dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        tmp_path = self.index_path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp_path, self.index_path)

    def _append_event_unlocked(self, event: str, bg_id: str, payload: Dict) -> None:
        record = {"time": self._now(), "event": event, "bg_id": bg_id}
        record.update(payload)
        with self.events_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _format_notification(self, record: BackgroundTaskRecord) -> str:
        exit_code = "" if record.exit_code is None else str(record.exit_code)
        return "\n".join([
            "<task_notification>",
            f"  <task_id>{record.id}</task_id>",
            f"  <status>{record.status}</status>",
            f"  <command>{record.command}</command>",
            f"  <exit_code>{exit_code}</exit_code>",
            f"  <output_path>{record.output_path}</output_path>",
            f"  <summary>{record.summary}</summary>",
            "</task_notification>",
        ])

    def _format_output(
        self,
        shell_name: str,
        command: str,
        exit_code: Optional[int],
        stdout: str,
        stderr: str,
    ) -> str:
        parts = [
            f"shell: {shell_name}",
            f"command: {command}",
            f"exit_code: {exit_code if exit_code is not None else 'unknown'}",
        ]
        if stdout:
            parts.append(f"stdout:\n{stdout}")
        if stderr:
            parts.append(f"stderr:\n{stderr}")
        if len(parts) == 3:
            parts.append("output: (no output)")
        return "\n\n".join(parts) + "\n"

    def _summarize_text(self, text: str) -> str:
        max_chars = int(self.config.get("MAX_NOTIFICATION_OUTPUT_CHARS", 1200))
        compact = " ".join(text.strip().split())
        if len(compact) > max_chars:
            return compact[:max_chars] + "..."
        return compact or "(no output)"

    def _read_output_tail(self, output_path: str, tail_chars: int) -> str:
        path = safe_path(output_path)
        if not path.exists():
            return ""
        if int(tail_chars or 0) <= 0:
            return ""
        text = path.read_text(encoding="utf-8", errors="replace")
        return text[-int(tail_chars):]

    def _timeout(self, timeout: Optional[int]) -> Optional[int]:
        if timeout and int(timeout) > 0:
            return int(timeout)
        default_timeout = int(self.config.get("DEFAULT_COMMAND_TIMEOUT_SECONDS", 0))
        return default_timeout if default_timeout > 0 else None

    def _normalize_bg_id(self, bg_id: str) -> str:
        bg_id = str(bg_id or "").strip()
        if not bg_id or "/" in bg_id or "\\" in bg_id or ".." in bg_id:
            raise ValueError(f"非法后台任务 ID: {bg_id}")
        return bg_id

    def _now(self) -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")


BACKGROUND_MANAGER = BackgroundManager()
