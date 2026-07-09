from managers.todo_manager import TODO
from managers.background_manager import BACKGROUND_MANAGER
from managers.compact_manager import COMPACT_MANAGER
from managers.cron_manager import CRON_MANAGER
from managers.memory_manager import MEMORY_MANAGER
from managers.team_manager import TEAM_MANAGER
from managers.worktree_manager import WORKTREE_MANAGER
from state.hook_state import HookContext, HookResult
from utils.config_handler import memory_config
from utils.logger_handler import logger
from utils.permission_check import check_permission


def log_session_start(context: HookContext):
    logger.info("[hook:%s] Agent 会话启动", context.event)


def memory_session_start_hook(context: HookContext):
    """会话启动时初始化 Memory 目录和索引。"""
    MEMORY_MANAGER.ensure_dirs()
    logger.info("[hook:%s] Memory 已初始化", context.event)
    return None


def cron_session_start_hook(context: HookContext):
    """会话启动时初始化 Cron Scheduler 存储。"""
    CRON_MANAGER.ensure_store()
    CRON_MANAGER.load_durable_jobs()
    logger.info("[hook:%s] Cron Scheduler 存储已初始化", context.event)
    return None


def team_session_start_hook(context: HookContext):
    """会话启动时初始化 Agent Teams 存储。"""
    TEAM_MANAGER.ensure_store()
    logger.info("[hook:%s] Agent Teams 存储已初始化", context.event)
    return None


def worktree_session_start_hook(context: HookContext):
    """会话启动时初始化 Worktree Isolation 存储。"""
    WORKTREE_MANAGER.ensure_store()
    logger.info("[hook:%s] Worktree Isolation 存储已初始化", context.event)
    return None


def log_before_model_call(context: HookContext):
    message_count = len(context.messages or [])
    logger.info(
        "[hook:%s] 准备调用模型: model=%s, messages=%s",
        context.event,
        context.model_id,
        message_count,
    )


def todo_reminder_hook(context: HookContext):
    """模型调用前注入计划提醒，保持 Agent Loop 不关心 TodoWrite 细节。"""
    if context.messages is None:
        return None
    if int(context.metadata.get("subagent_depth", 0)) > 0:
        return None

    reminder = TODO.reminder()
    if not reminder:
        return None

    logger.info("[hook:%s] 注入 Todo reminder", context.event)
    context.messages.append({"role": "user", "content": reminder})
    return None


def background_before_model_call_hook(context: HookContext):
    """模型调用前注入已完成的后台任务通知。"""
    if context.messages is None:
        return None
    if int(context.metadata.get("subagent_depth", 0)) > 0:
        return None

    notifications = BACKGROUND_MANAGER.drain_notifications()
    if not notifications:
        return None

    logger.info("[hook:%s] 注入后台任务通知: count=%s", context.event, len(notifications))
    context.messages.append({
        "role": "user",
        "content": "\n\n".join(notifications),
    })
    return None


def team_before_model_call_hook(context: HookContext):
    """模型调用前把 Lead 收件箱消息注入上下文。"""
    if context.messages is None:
        return None
    if int(context.metadata.get("subagent_depth", 0)) > 0:
        return None

    inbox_text = TEAM_MANAGER.drain_lead_inbox_for_prompt()
    if not inbox_text:
        return None

    logger.info("[hook:%s] 注入团队 inbox 消息", context.event)
    context.messages.append({"role": "user", "content": inbox_text})
    return None


def memory_before_model_call_hook(context: HookContext):
    """模型调用前按需注入相关长期记忆正文。"""
    if context.messages is None:
        return None
    if int(context.metadata.get("subagent_depth", 0)) > 0 and not memory_config.get("ALLOW_SUBAGENT_MEMORY_READ", True):
        return None

    MEMORY_MANAGER.inject_relevant_memories(
        context.messages,
        client=context.metadata.get("client"),
        model_id=context.model_id,
    )
    return None


def memory_stop_extract_hook(context: HookContext):
    """会话结束时尝试自动提取长期记忆，不影响主回答返回。"""
    if context.messages is None:
        return None
    if int(context.metadata.get("subagent_depth", 0)) > 0 and not memory_config.get("ALLOW_SUBAGENT_MEMORY_WRITE", False):
        return None

    MEMORY_MANAGER.extract_memories(
        context.messages,
        client=context.metadata.get("client"),
        model_id=context.model_id,
    )
    return None





def log_after_model_call(context: HookContext):
    logger.info(
        "[hook:%s] 模型返回: finish_reason=%s, tool_calls=%s",
        context.event,
        context.metadata.get("finish_reason"),
        context.metadata.get("tool_call_count", 0),
    )


def todo_round_tracker_hook(context: HookContext):
    """模型返回后统计本轮是否更新了计划。

    这里按模型轮次统计，不放在 PostToolUse，避免一轮多个工具时重复计数。
    """
    tool_names = context.metadata.get("tool_names", [])
    if not tool_names:
        return None
    if "todo" in tool_names:
        return None

    TODO.note_round_without_update()
    return None


def log_pre_tool_use(context: HookContext):
    if context.tool_name == "todo":
        items = context.tool_input.get("items", [])
        logger.info(
            "[hook:%s] 工具执行前: todo, items=%s",
            context.event,
            len(items) if isinstance(items, list) else 0,
        )
        return None
    if context.tool_name == "save_memory":
        logger.info(
            "[hook:%s] 工具执行前: save_memory, scope=%s, type=%s, name=%s",
            context.event,
            context.tool_input.get("scope"),
            context.tool_input.get("type"),
            context.tool_input.get("name"),
        )
        return None
    if context.tool_name == "forget_memory":
        logger.info(
            "[hook:%s] 工具执行前: forget_memory, scope=%s, target=%s",
            context.event,
            context.tool_input.get("scope"),
            context.tool_input.get("name_or_path"),
        )
        return None

    logger.info(
        "[hook:%s] 工具执行前: %s, args=%s",
        context.event,
        context.tool_name,
        context.tool_input,
    )


def permission_check_hook(context: HookContext):
    """最终 PreToolUse hook：检查经过其他 hook 改写后的工具参数。"""
    permission = check_permission(context.tool_name or "", context.tool_input)
    if permission.allowed:
        if context.tool_name == "todo":
            return None
        logger.info(
            "[hook:%s] 权限通过: %s, 原因: %s",
            context.event,
            context.tool_name,
            permission.reason,
        )
        return None

    reason = f"Permission denied: {permission.reason}"
    logger.warning(
        "[hook:%s] 权限拒绝: %s, 原因: %s",
        context.event,
        context.tool_name,
        permission.reason,
    )
    return HookResult(blocked=True, block_reason=reason)


def log_post_tool_use(context: HookContext):
    output_length = len(context.tool_output or "")
    logger.info(
        "[hook:%s] 工具执行后: %s, output_length=%s",
        context.event,
        context.tool_name,
        output_length,
    )

def compact_before_model_call_hook(context: HookContext):
    """模型调用前压缩上下文，让 Agent Loop 不关心 compact 细节。"""
    if context.messages is None:
        return None

    manager = context.metadata.get("compact_manager") or COMPACT_MANAGER
    client = context.metadata.get("client")
    subagent_depth = int(context.metadata.get("subagent_depth", 0))
    allow_llm = subagent_depth == 0 or context.metadata.get("allow_subagent_llm_compact", False)
    manager.pre_model_compact(
        context.messages,
        client=client,
        model_id=context.model_id,
        allow_llm=allow_llm,
    )
    return None

def compact_post_tool_use_hook(context: HookContext):
    """工具执行后压缩超大输出，避免大结果直接写入 messages。"""
    if not context.tool_output:
        return None

    manager = context.metadata.get("compact_manager") or COMPACT_MANAGER
    compacted = manager.persist_tool_output(
        context.tool_output,
        tool_name=context.tool_name or "tool",
        tool_call_id=str(context.metadata.get("tool_call_id") or context.tool_name or "tool"),
    )
    if compacted != context.tool_output:
        logger.info("[hook:%s] 工具输出已由 compact hook 落盘: %s", context.event, context.tool_name)
        return HookResult(updated_output=compacted)
    return None
