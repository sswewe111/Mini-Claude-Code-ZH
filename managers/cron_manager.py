import json
import os
import threading
import time
from collections import deque
from contextlib import contextmanager
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Callable, Deque, Dict, Iterable, List, Optional, Set, Tuple

from state.cron_state import CronJobRecord, FiredCronEvent
from utils.config_handler import cron_config
from utils.logger_handler import logger
from utils.path_sandbox import safe_path


AgentRunner = Callable[[object, str, object], str]


class CronManager:
    """进程内 Cron 调度器：按时间生产工作，空闲时交付给 Agent。"""

    FIELD_RANGES: Tuple[Tuple[int, int], ...] = (
        (0, 59),   # minute
        (0, 23),   # hour
        (1, 31),   # day of month
        (1, 12),   # month
        (0, 7),    # day of week, 0/7 = Sunday
    )

    def __init__(self, config: Optional[Dict] = None) -> None:
        self.config = config or cron_config
        self.root = safe_path(str(self.config.get("CRON_TASK_DIR", ".runtime-tasks")))
        self.task_path = safe_path(str(self.config.get("CRON_TASK_FILE", ".runtime-tasks/scheduled_tasks.json")))
        self.event_path = safe_path(str(self.config.get("CRON_EVENT_FILE", ".runtime-tasks/scheduled_events.jsonl")))
        self.id_prefix = str(self.config.get("CRON_ID_PREFIX", "cron_"))
        self.session_id_prefix = str(self.config.get("CRON_SESSION_ID_PREFIX", "cron_session_"))
        self.event_id_prefix = str(self.config.get("CRON_EVENT_ID_PREFIX", "cron_evt_"))
        self.lock = threading.RLock()
        self.agent_lock = threading.Lock()
        self.durable_jobs: Dict[str, CronJobRecord] = {}
        self.session_jobs: Dict[str, CronJobRecord] = {}
        self.queue: Deque[FiredCronEvent] = deque()
        self.scheduler_started = False
        self.client = None
        self.model_id = ""
        self.hook_manager = None
        self.runner: Optional[AgentRunner] = None
        self._next_session_id = 1
        self._next_event_id = 1

    def ensure_store(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.task_path.parent.mkdir(parents=True, exist_ok=True)
        self.event_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.task_path.exists():
            self._write_index({
                "version": 1,
                "next_id": 1,
                "updated_at": self._now(),
                "tasks": {},
            })
        if not self.event_path.exists():
            self.event_path.touch()

    def start(
        self,
        client,
        model_id: str,
        hook_manager=None,
        workdir: str = "",
        runner: Optional[AgentRunner] = None,
    ) -> None:
        if not self.config.get("ENABLE_CRON_SCHEDULER", True):
            logger.info("Cron Scheduler 未启用")
            return

        with self.lock:
            self.client = client
            self.model_id = model_id
            self.hook_manager = hook_manager
            self.runner = runner
            self.ensure_store()
            self.load_durable_jobs()
            if self.scheduler_started:
                return
            self.scheduler_started = True

        threading.Thread(
            target=self._scheduler_loop,
            daemon=True,
            name="cron-scheduler",
        ).start()
        threading.Thread(
            target=self._queue_processor_loop,
            daemon=True,
            name="cron-queue-processor",
        ).start()
        logger.info("Cron Scheduler 已启动: workdir=%s", workdir or Path.cwd())

    @contextmanager
    def agent_execution(self):
        self.agent_lock.acquire()
        try:
            yield
        finally:
            self.agent_lock.release()

    def create(
        self,
        cron: str,
        prompt: str,
        recurring: bool = True,
        durable: bool = True,
    ) -> str:
        cron = str(cron or "").strip()
        prompt = str(prompt or "").strip()
        if not prompt:
            raise ValueError("定时任务 prompt 不能为空")
        err = self.validate_cron(cron)
        if err:
            raise ValueError(err)
        if durable and not self.config.get("ENABLE_DURABLE_CRON", True):
            raise ValueError("Durable Cron 未启用")
        if not durable and not self.config.get("ENABLE_SESSION_CRON", True):
            raise ValueError("Session-only Cron 未启用")

        self.ensure_store()
        with self.lock:
            self.load_durable_jobs()
            total = len(self.durable_jobs) + len(self.session_jobs)
            max_jobs = int(self.config.get("MAX_CRON_JOBS", 50))
            if total >= max_jobs:
                raise ValueError(f"定时任务数量已达上限: {max_jobs}")

            now = self._now()
            job_id = self._next_durable_id_unlocked() if durable else self._next_session_id_unlocked()
            job = CronJobRecord(
                id=job_id,
                cron=cron,
                prompt=prompt,
                recurring=bool(recurring),
                durable=bool(durable),
                created_at=now,
                updated_at=now,
            )
            if durable:
                self.durable_jobs[job_id] = job
                self._save_durable_jobs_unlocked()
            else:
                self.session_jobs[job_id] = job
            self._append_event_unlocked("create", "", {
                "cron_id": job_id,
                "cron": cron,
                "recurring": job.recurring,
                "durable": job.durable,
            })

        return "\n".join([
            f"已创建定时任务: {job.id}",
            f"cron: {job.cron}",
            f"recurring: {job.recurring}",
            f"durable: {job.durable}",
            f"prompt: {self._compact_prompt(job.prompt)}",
        ])

    def cancel(self, cron_id: str) -> str:
        cron_id = self._normalize_id(cron_id)
        self.ensure_store()
        with self.lock:
            self.load_durable_jobs()
            removed = self.durable_jobs.pop(cron_id, None)
            if removed:
                self._save_durable_jobs_unlocked()
            else:
                removed = self.session_jobs.pop(cron_id, None)
            if not removed:
                raise ValueError(f"定时任务不存在: {cron_id}")
            self._append_event_unlocked("cancel", "", {"cron_id": cron_id})
        return f"已取消定时任务: {cron_id}"

    def list_all(self, include_session: bool = True) -> str:
        self.ensure_store()
        with self.lock:
            self.load_durable_jobs()
            jobs = list(self.durable_jobs.values())
            if include_session:
                jobs.extend(self.session_jobs.values())
        jobs = sorted(jobs, key=lambda job: (not job.durable, job.id))
        if not jobs:
            return "当前没有定时任务。"

        lines = [f"定时任务：{len(jobs)}"]
        for job in jobs:
            scope = "durable" if job.durable else "session"
            recurring = "recurring" if job.recurring else "one-shot"
            enabled = "enabled" if job.enabled else "disabled"
            last = job.last_fired_at or "-"
            lines.append(
                f"- {job.id} [{scope} {recurring} {enabled}] {job.cron} "
                f"fire_count={job.fire_count} last={last} :: {self._compact_prompt(job.prompt)}"
            )
        return "\n".join(lines)

    def load_durable_jobs(self) -> None:
        self.ensure_store()
        with self.lock:
            index = self._read_index_unlocked()
            valid_jobs: Dict[str, CronJobRecord] = {}
            changed = False
            for cron_id, data in list(index.get("tasks", {}).items()):
                try:
                    job = CronJobRecord.from_dict(data)
                    if not job.id:
                        job.id = str(cron_id)
                    err = self.validate_cron(job.cron)
                    if err:
                        logger.warning("跳过非法 durable cron: %s, %s", cron_id, err)
                        changed = True
                        continue
                    job.durable = True
                    valid_jobs[job.id] = job
                except Exception as exc:
                    logger.warning("跳过损坏 durable cron: %s, %s", cron_id, exc)
                    changed = True
            self.durable_jobs = valid_jobs
            self._next_session_id = max(self._next_session_id, self._max_numeric_id(valid_jobs) + 1)
            if changed:
                self._save_durable_jobs_unlocked()

    def validate_cron(self, expr: str) -> Optional[str]:
        fields = str(expr or "").strip().split()
        if len(fields) != 5:
            return "cron 表达式必须是五段式：分钟 小时 日 月 星期"
        for index, field in enumerate(fields):
            try:
                self._parse_field(field, *self.FIELD_RANGES[index], normalize_dow=index == 4)
            except ValueError as exc:
                return f"cron 第 {index + 1} 段非法: {exc}"
        return None

    def cron_matches(self, expr: str, dt: datetime) -> bool:
        fields = str(expr or "").strip().split()
        if len(fields) != 5:
            return False
        try:
            minute, hour, dom, month, dow = fields
            dow_val = (dt.weekday() + 1) % 7
            minute_ok = dt.minute in self._parse_field(minute, 0, 59)
            hour_ok = dt.hour in self._parse_field(hour, 0, 23)
            dom_ok = dt.day in self._parse_field(dom, 1, 31)
            month_ok = dt.month in self._parse_field(month, 1, 12)
            dow_ok = dow_val in self._parse_field(dow, 0, 7, normalize_dow=True)
        except ValueError:
            return False

        if not (minute_ok and hour_ok and month_ok):
            return False
        dom_unconstrained = dom == "*"
        dow_unconstrained = dow == "*"
        if dom_unconstrained and dow_unconstrained:
            return True
        if dom_unconstrained:
            return dow_ok
        if dow_unconstrained:
            return dom_ok
        return dom_ok or dow_ok

    def enqueue_due_jobs(self, now: Optional[datetime] = None) -> int:
        now = now or datetime.now().astimezone()
        marker = now.strftime("%Y-%m-%d %H:%M")
        fired = 0
        self.ensure_store()
        with self.lock:
            self.load_durable_jobs()
            for table in (self.durable_jobs, self.session_jobs):
                for job in list(table.values()):
                    try:
                        if not job.enabled or not self.cron_matches(job.cron, now):
                            continue
                        if job.last_fire_marker == marker:
                            continue
                        event = FiredCronEvent(
                            event_id=self._next_event_id_unlocked(),
                            job_id=job.id,
                            cron=job.cron,
                            prompt=job.prompt,
                            fired_at=self._now(now),
                            durable=job.durable,
                            recurring=job.recurring,
                        )
                        self.queue.append(event)
                        job.last_fire_marker = marker
                        job.last_fired_at = event.fired_at
                        job.fire_count += 1
                        job.updated_at = event.fired_at
                        fired += 1
                        self._append_event_unlocked("fire", event.event_id, {
                            "cron_id": job.id,
                            "cron": job.cron,
                            "marker": marker,
                        })
                        if not job.recurring:
                            table.pop(job.id, None)
                    except Exception as exc:
                        logger.exception("cron job 触发失败: %s, %s", job.id, exc)
            self._save_durable_jobs_unlocked()
        return fired

    def has_pending_events(self) -> bool:
        with self.lock:
            return bool(self.queue)

    def consume_triggered_events(self, limit: Optional[int] = None) -> List[FiredCronEvent]:
        max_items = int(limit or self.config.get("MAX_TRIGGERED_EVENTS_PER_TURN", 5))
        events: List[FiredCronEvent] = []
        with self.lock:
            while self.queue and len(events) < max_items:
                event = self.queue.popleft()
                events.append(event)
                self._append_event_unlocked("deliver", event.event_id, {"cron_id": event.job_id})
        return events

    def format_events_as_user_message(self, events: Iterable[FiredCronEvent]) -> str:
        blocks = []
        for event in events:
            blocks.append("\n".join([
                "<scheduled_task>",
                f"  <event_id>{escape(event.event_id)}</event_id>",
                f"  <cron_id>{escape(event.job_id)}</cron_id>",
                f"  <cron>{escape(event.cron)}</cron>",
                f"  <fired_at>{escape(event.fired_at)}</fired_at>",
                f"  <prompt>{escape(event.prompt)}</prompt>",
                "</scheduled_task>",
            ]))
        return "\n\n".join(blocks)

    def _scheduler_loop(self) -> None:
        interval = float(self.config.get("CHECK_INTERVAL_SECONDS", 1))
        while True:
            time.sleep(max(interval, 0.1))
            try:
                count = self.enqueue_due_jobs(datetime.now().astimezone())
                if count:
                    logger.info("Cron Scheduler 入队任务: count=%s", count)
            except Exception:
                logger.exception("cron scheduler tick failed")

    def _queue_processor_loop(self) -> None:
        interval = float(self.config.get("QUEUE_PROCESSOR_INTERVAL_SECONDS", 0.2))
        while True:
            time.sleep(max(interval, 0.1))
            if not self.has_pending_events():
                continue
            if not self.agent_lock.acquire(blocking=False):
                continue
            try:
                if self.has_pending_events():
                    self._run_scheduled_agent_turn()
            finally:
                self.agent_lock.release()

    def _run_scheduled_agent_turn(self) -> None:
        if not self.runner:
            logger.warning("Cron 事件等待交付，但未配置 Agent runner")
            return
        try:
            result = self.runner(self.client, self.model_id, self.hook_manager)
            logger.info("Cron scheduled agent turn 完成: output_length=%s", len(result or ""))
        except Exception:
            logger.exception("Cron scheduled agent turn failed")

    def _parse_field(self, field: str, min_value: int, max_value: int, normalize_dow: bool = False) -> Set[int]:
        field = str(field or "").strip()
        if not field:
            raise ValueError("字段为空")
        values: Set[int] = set()
        for raw_part in field.split(","):
            part = raw_part.strip()
            if not part:
                raise ValueError("列表项为空")
            base, step = self._split_step(part)
            if base == "*":
                start, end = min_value, max_value
            elif "-" in base:
                start_text, end_text = base.split("-", 1)
                start = self._parse_int(start_text, min_value, max_value)
                end = self._parse_int(end_text, min_value, max_value)
                if start > end:
                    raise ValueError(f"范围起点大于终点: {base}")
            else:
                if step is not None:
                    raise ValueError(f"单值不支持步长: {part}")
                start = end = self._parse_int(base, min_value, max_value)
            if step is not None and step <= 0:
                raise ValueError("步长必须大于 0")
            for value in range(start, end + 1, step or 1):
                values.add(0 if normalize_dow and value == 7 else value)
        return values

    def _split_step(self, part: str) -> Tuple[str, Optional[int]]:
        if "/" not in part:
            return part, None
        base, step_text = part.split("/", 1)
        if not base or not step_text:
            raise ValueError(f"步长格式非法: {part}")
        return base, self._parse_int(step_text, 1, 999999)

    def _parse_int(self, text: str, min_value: int, max_value: int) -> int:
        try:
            value = int(str(text).strip())
        except ValueError as exc:
            raise ValueError(f"不是整数: {text}") from exc
        if value < min_value or value > max_value:
            raise ValueError(f"值越界: {value}，允许 {min_value}-{max_value}")
        return value

    def _next_durable_id_unlocked(self) -> str:
        index = self._read_index_unlocked()
        next_id = int(index.get("next_id", 1))
        job_id = f"{self.id_prefix}{next_id:06d}"
        index["next_id"] = next_id + 1
        index["updated_at"] = self._now()
        self._write_index_unlocked(index)
        return job_id

    def _next_session_id_unlocked(self) -> str:
        while True:
            job_id = f"{self.session_id_prefix}{self._next_session_id:06d}"
            self._next_session_id += 1
            if job_id not in self.session_jobs and job_id not in self.durable_jobs:
                return job_id

    def _next_event_id_unlocked(self) -> str:
        event_id = f"{self.event_id_prefix}{self._next_event_id:06d}"
        self._next_event_id += 1
        return event_id

    def _max_numeric_id(self, jobs: Dict[str, CronJobRecord]) -> int:
        max_id = 0
        for job_id in jobs:
            suffix = job_id.rsplit("_", 1)[-1]
            if suffix.isdigit():
                max_id = max(max_id, int(suffix))
        return max_id

    def _save_durable_jobs_unlocked(self) -> None:
        index = self._read_index_unlocked()
        index["tasks"] = {job_id: job.to_dict() for job_id, job in sorted(self.durable_jobs.items())}
        index["updated_at"] = self._now()
        self._write_index_unlocked(index)

    def _read_index_unlocked(self) -> Dict:
        try:
            return json.loads(self.task_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"version": 1, "next_id": 1, "tasks": {}, "updated_at": self._now()}
        except json.JSONDecodeError as exc:
            raise ValueError(f"定时任务索引损坏: {self.task_path}") from exc

    def _write_index(self, data: Dict) -> None:
        with self.lock:
            self._write_index_unlocked(data)

    def _write_index_unlocked(self, data: Dict) -> None:
        self.task_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.task_path.with_suffix(self.task_path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp_path, self.task_path)

    def _append_event_unlocked(self, event: str, event_id: str, payload: Dict) -> None:
        self.event_path.parent.mkdir(parents=True, exist_ok=True)
        record = {"time": self._now(), "event": event}
        if event_id:
            record["event_id"] = event_id
        record.update(payload)
        with self.event_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _normalize_id(self, cron_id: str) -> str:
        cron_id = str(cron_id or "").strip()
        if not cron_id or "/" in cron_id or "\\" in cron_id or ".." in cron_id:
            raise ValueError(f"非法定时任务 ID: {cron_id}")
        return cron_id

    def _compact_prompt(self, prompt: str, max_chars: int = 120) -> str:
        compact = " ".join(str(prompt or "").split())
        return compact if len(compact) <= max_chars else compact[:max_chars] + "..."

    def _now(self, dt: Optional[datetime] = None) -> str:
        value = dt or datetime.now().astimezone()
        return value.astimezone().isoformat(timespec="seconds")


CRON_MANAGER = CronManager()
