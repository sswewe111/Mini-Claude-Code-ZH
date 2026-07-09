from managers.todo_manager import TODO
from managers.skill_manager import SKILL_REGISTRY
from managers.compact_manager import COMPACT_MANAGER
from managers.memory_manager import MEMORY_MANAGER
from managers.task_manager import TASK_MANAGER
from managers.background_manager import BACKGROUND_MANAGER
from managers.cron_manager import CRON_MANAGER
from managers.team_manager import TEAM_MANAGER
from handlers.worktree_handlers import WORKTREE_HANDLERS
from tools.bash_tools import run_bash
from tools.file_tools import edit_file, read_file, write_file
from utils.logger_handler import logger


def handle_bash(args: dict) -> str:
    if args.get("run_in_background"):
        return BACKGROUND_MANAGER.run_command(
            command=args["command"],
            owner=args.get("background_owner", "main"),
        )
    return run_bash(args["command"])


def handle_read_file(args: dict) -> str:
    return read_file(args["path"], args.get("limit"))


def handle_write_file(args: dict) -> str:
    return write_file(args["path"], args["content"])


def handle_edit_file(args: dict) -> str:
    return edit_file(args["path"], args["old_text"], args["new_text"])


def handle_todo(args: dict) -> str:
    result = TODO.update(args["items"])
    logger.info("Todo 计划状态:\n%s", result)
    return result


def handle_load_skill(args: dict) -> str:
    name = args.get("name", "")
    logger.info("加载技能: %s", name)
    return SKILL_REGISTRY.load_skill(name)


def handle_compact(args: dict) -> str:
    focus = args.get("focus", "")
    return COMPACT_MANAGER.request_manual_compact(focus)


def handle_save_memory(args: dict) -> str:
    return MEMORY_MANAGER.save_memory(
        name=args["name"],
        scope=args["scope"],
        type=args["type"],
        description=args["description"],
        content=args["content"],
    )


def handle_forget_memory(args: dict) -> str:
    return MEMORY_MANAGER.forget_memory(
        name_or_path=args["name_or_path"],
        scope=args["scope"],
        reason=args.get("reason", ""),
    )


def handle_task_create(args: dict) -> str:
    return TASK_MANAGER.create(
        subject=args["subject"],
        description=args.get("description", ""),
        blocked_by=args.get("blocked_by") or [],
        metadata=args.get("metadata") or {},
    )


def handle_task_list(args: dict) -> str:
    return TASK_MANAGER.list_all(
        include_completed=args.get("include_completed", True),
        owner=args.get("owner"),
        status=args.get("status"),
    )


def handle_task_get(args: dict) -> str:
    return TASK_MANAGER.get(args["task_id"])


def handle_task_update(args: dict) -> str:
    changes = {}
    for key in ("subject", "description", "active_form", "blocked_by", "metadata", "owner", "status"):
        if key in args:
            changes[key] = args.get(key)
    return TASK_MANAGER.update(args["task_id"], **changes)


def handle_task_claim(args: dict) -> str:
    return TASK_MANAGER.claim(
        task_id=args["task_id"],
        owner=args.get("owner", "main"),
    )


def handle_task_complete(args: dict) -> str:
    return TASK_MANAGER.complete(
        task_id=args["task_id"],
        owner=args.get("owner"),
        summary=args.get("summary", ""),
    )


def handle_task_cancel(args: dict) -> str:
    return TASK_MANAGER.cancel(
        task_id=args["task_id"],
        reason=args.get("reason", ""),
    )


def handle_background_list(args: dict) -> str:
    return BACKGROUND_MANAGER.list_all(
        include_completed=args.get("include_completed", True),
    )


def handle_background_get(args: dict) -> str:
    return BACKGROUND_MANAGER.get(
        bg_id=args["bg_id"],
        tail_chars=args.get("tail_chars", 2000),
    )


def handle_schedule_cron(args: dict) -> str:
    return CRON_MANAGER.create(
        cron=args["cron"],
        prompt=args["prompt"],
        recurring=args.get("recurring", True),
        durable=args.get("durable", True),
    )


def handle_list_crons(args: dict) -> str:
    return CRON_MANAGER.list_all(
        include_session=args.get("include_session", True),
    )


def handle_cancel_cron(args: dict) -> str:
    return CRON_MANAGER.cancel(args["cron_id"])


def handle_spawn_teammate(args: dict, runtime_context=None) -> str:
    if runtime_context:
        TEAM_MANAGER.start(
            client=runtime_context.client,
            model_id=runtime_context.model_id,
            hook_manager=runtime_context.hook_manager,
            workdir=runtime_context.workdir,
        )
    return TEAM_MANAGER.spawn(
        name=args["name"],
        role=args["role"],
        prompt=args["prompt"],
    )


def handle_team_send_message(args: dict, runtime_context=None) -> str:
    return TEAM_MANAGER.send_message(
        to=args["to"],
        content=args["content"],
        msg_type=args.get("msg_type", "message"),
    )


def handle_team_broadcast(args: dict, runtime_context=None) -> str:
    return TEAM_MANAGER.broadcast(
        content=args["content"],
        recipients=args.get("recipients"),
    )


def handle_team_check_inbox(args: dict, runtime_context=None) -> str:
    return TEAM_MANAGER.check_inbox(agent=args.get("agent"))


def handle_team_list(args: dict, runtime_context=None) -> str:
    return TEAM_MANAGER.list_all()


def handle_team_request_shutdown(args: dict, runtime_context=None) -> str:
    return TEAM_MANAGER.request_shutdown(
        name=args["name"],
        reason=args.get("reason", ""),
    )


def handle_team_review_plan(args: dict, runtime_context=None) -> str:
    return TEAM_MANAGER.review_plan(
        request_id=args["request_id"],
        approve=bool(args["approve"]),
        feedback=args.get("feedback", ""),
    )


def handle_team_protocol_status(args: dict, runtime_context=None) -> str:
    return TEAM_MANAGER.protocol_status(
        request_id=args.get("request_id", ""),
        include_resolved=args.get("include_resolved", True),
    )


def handle_task(args: dict, runtime_context=None) -> str:
    from subagents.task_subagent import run_task_subagent

    description = args["description"]
    expected_output = args.get("expected_output", "")
    logger.info("[subagent] task 工具启动子 Agent")
    result = run_task_subagent(
        description=description,
        expected_output=expected_output,
        runtime_context=runtime_context,
    )
    logger.info("[subagent] task 工具返回子 Agent 结果: length=%s", len(result))
    return result


BASE_HANDLERS = {
    "bash": handle_bash,
    "read_file": handle_read_file,
    "write_file": handle_write_file,
    "edit_file": handle_edit_file,
    "todo": handle_todo,
    "task": handle_task,
    "load_skill": handle_load_skill,
    "compact": handle_compact,
    "save_memory": handle_save_memory,
    "forget_memory": handle_forget_memory,
    "task_create": handle_task_create,
    "task_list": handle_task_list,
    "task_get": handle_task_get,
    "task_update": handle_task_update,
    "task_claim": handle_task_claim,
    "task_complete": handle_task_complete,
    "task_cancel": handle_task_cancel,
    "background_list": handle_background_list,
    "background_get": handle_background_get,
    "schedule_cron": handle_schedule_cron,
    "list_crons": handle_list_crons,
    "cancel_cron": handle_cancel_cron,
    "spawn_teammate": handle_spawn_teammate,
    "team_send_message": handle_team_send_message,
    "team_broadcast": handle_team_broadcast,
    "team_check_inbox": handle_team_check_inbox,
    "team_list": handle_team_list,
    "team_request_shutdown": handle_team_request_shutdown,
    "team_review_plan": handle_team_review_plan,
    "team_protocol_status": handle_team_protocol_status,
}
BASE_HANDLERS.update(WORKTREE_HANDLERS)
