from typing import Dict, List, Optional

from state.agent_state import PlanItem, PlanningState
from utils.config_handler import todo_config


VALID_STATUSES = {"pending", "in_progress", "completed"}
STATUS_LABELS = {
    "pending": "待处理",
    "in_progress": "进行中",
    "completed": "已完成",
}
MAX_TODO_ITEMS = 12


class TodoManager:
    """管理当前会话的短期计划。

    Todo 不读写文件，也不执行命令，只把模型给出的计划保存在内存中。
    """

    def __init__(self) -> None:
        self.state = PlanningState()
        self.reminder_interval = int(todo_config.get("PLAN_REMINDER_INTERVAL", 3))

    def update(self, items: List[Dict]) -> str:
        """重写当前计划，并返回可读的计划视图。"""
        plan_items = self._validate_items(items)
        self.state.items = plan_items
        self.state.rounds_since_update = 0
        return self.render()

    def note_round_without_update(self) -> None:
        """记录一轮没有更新计划。没有计划时不累计，避免简单任务被提醒。"""
        if self.state.items:
            self.state.rounds_since_update += 1

    def reminder(self) -> Optional[str]:
        """连续多轮未更新计划时，提醒模型刷新当前计划。"""
        if not self.state.items:
            return None
        if self.state.rounds_since_update < self.reminder_interval:
            return None
        return "<reminder>请在继续执行前调用 todo 工具刷新当前计划状态。</reminder>"

    def render(self) -> str:
        """把当前计划渲染成工具结果，供模型和终端日志阅读。"""
        if not self.state.items:
            return "当前没有计划。"

        completed = sum(1 for item in self.state.items if item.status == "completed")
        total = len(self.state.items)
        summary = f"当前计划：{completed}/{total} 已完成"
        if completed == total:
            summary += "，全部完成"
        lines = [summary]

        for index, item in enumerate(self.state.items, start=1):
            marker = {
                "pending": "[ ]",
                "in_progress": "[>]",
                "completed": "[x]",
            }[item.status]
            status_label = STATUS_LABELS[item.status]
            suffix = f" - {item.active_form}" if item.active_form else ""
            lines.append(f"{index}. {marker} {item.content}（状态: {status_label}）{suffix}")
        return "\n".join(lines)

    def _validate_items(self, items: List[Dict]) -> List[PlanItem]:
        if not isinstance(items, list):
            raise ValueError("todo items 必须是列表")
        if len(items) > MAX_TODO_ITEMS:
            raise ValueError(f"todo items 最多支持 {MAX_TODO_ITEMS} 项")

        plan_items: List[PlanItem] = []
        in_progress_count = 0
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"第 {index} 个 todo item 必须是对象")

            content = str(item.get("content", "")).strip()
            status = str(item.get("status", "")).strip()
            active_form = str(item.get("activeForm", "")).strip()

            if not content:
                raise ValueError(f"第 {index} 个 todo item 缺少 content")
            if status not in VALID_STATUSES:
                raise ValueError(
                    f"第 {index} 个 todo item status 必须是 pending、in_progress 或 completed"
                )
            if status == "in_progress":
                in_progress_count += 1

            plan_items.append(
                PlanItem(content=content, status=status, active_form=active_form)
            )

        if in_progress_count > 1:
            raise ValueError("同一时间最多只能有一个 in_progress 计划项")
        return plan_items


TODO = TodoManager()
