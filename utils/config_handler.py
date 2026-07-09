from copy import deepcopy
from typing import Any, Dict, Optional

try:
    import yaml
except ModuleNotFoundError:
    yaml = None

from utils.path_sandbox import safe_path


DEFAULT_PERMISSION_CONFIG: Dict[str, Any] = {
    "tools": {
        "allow": [
            "bash",
            "read_file",
            "write_file",
            "edit_file",
            "todo",
            "task",
            "load_skill",
            "compact",
            "save_memory",
            "forget_memory",
            "task_create",
            "task_list",
            "task_get",
            "task_update",
            "task_claim",
            "task_complete",
            "task_cancel",
            "background_list",
            "background_get",
            "schedule_cron",
            "list_crons",
            "cancel_cron",
            "spawn_teammate",
            "team_send_message",
            "team_broadcast",
            "team_check_inbox",
            "team_list",
            "team_request_shutdown",
            "team_review_plan",
            "team_protocol_status",
            "team_submit_plan",
            "worktree_create",
            "worktree_bind",
            "worktree_list",
            "worktree_status",
            "worktree_keep",
            "worktree_remove",
        ],
        "deny": [],
    },
    "dangerous_commands": [
        "rm -rf",
        "rm",
        "unlink",
        "shred",
        "trash",
        "trash-put",
        "gio trash",
        "del",
        "erase",
        "rd",
        "rmdir",
        "Remove-Item",
        "Remove-ItemProperty",
        "ri",
        "Remove-Variable",
        "Clear-Content",
        "Remove-Content",
        "Remove-Module",
        "Remove-PSDrive",
        "Remove-LocalUser",
        "Remove-LocalGroup",
        "Remove-LocalGroupMember",
        "[System.IO.File]::Delete",
        "[System.IO.Directory]::Delete",
        ".Delete(",
        "os.remove",
        "os.unlink",
        "os.rmdir",
        "os.removedirs",
        "shutil.rmtree",
        "Path.unlink",
        ".unlink(",
        ".rmdir(",
        "send2trash",
        "fs.unlink",
        "fs.unlinkSync",
        "unlinkSync",
        "fs.rm",
        "fs.rmSync",
        "rmSync",
        "fs.rmdir",
        "fs.rmdirSync",
        "rmdirSync",
        "Deno.remove",
        "Deno.removeSync",
        "File.delete",
        "Files.delete",
        "deleteFile",
        "deleteDirectory",
        "deleteDir",
        "deleteSync",
        "delete(",
        "-delete",
        "git clean",
        "git reset --hard",
        "/MIR",
        "Format-Volume",
        "shutdown",
        "reboot",
    ],
    "approval": {
        "mode": "ask",
        "required_tools": ["write_file", "edit_file", "worktree_remove"],
    },
}


DEFAULT_HOOKS_CONFIG: Dict[str, Any] = {
    "enabled": False,
    "timeout_seconds": 30,
    "trust": {
        "require_marker": False,
        "marker_path": ".mini_claude_code_trusted",
    },
    "events": {},
}


DEFAULT_TODO_CONFIG: Dict[str, Any] = {
    "PLAN_REMINDER_INTERVAL": 3,
}


DEFAULT_SUBAGENT_CONFIG: Dict[str, Any] = {
    "SUBAGENT_MODE": "non_fork",
    "MAX_SUBAGENT_TURNS": 20,
    "SUBAGENT_RESULT_MAX_CHARS": 6000,
    "ALLOWED_SUBAGENT_TOOLS": ["bash", "read_file", "write_file", "edit_file", "load_skill"],
    "FORK_CONTEXT_MAX_MESSAGES": 12,
    "FORK_CONTEXT_MAX_CHARS": 12000,
    "FORK_INCLUDE_TOOL_RESULTS": False,
    "FORK_SUMMARIZE_PARENT_CONTEXT": True,
    "FORK_REQUIRE_SELF_CONTAINED_DESCRIPTION": True,
}


DEFAULT_SKILL_CONFIG: Dict[str, Any] = {
    "SKILLS_ROOT": "skills",
    "SKILL_ENTRY_FILE": "SKILL.md",
    "INJECT_SKILL_CATALOG": True,
    "MAX_SKILL_DESCRIPTION_CHARS": 180,
    "MAX_SKILL_CONTENT_CHARS": 12000,
    "ALLOW_SUBAGENT_LOAD_SKILL": True,
}


DEFAULT_COMPACT_CONFIG: Dict[str, Any] = {
    "ENABLE_AUTO_COMPACT": True,
    "MAX_MESSAGES_BEFORE_SNIP": 60,
    "KEEP_HEAD_MESSAGES": 3,
    "KEEP_TAIL_MESSAGES": 45,
    "KEEP_RECENT_TOOL_RESULTS": 4,
    "LARGE_TOOL_OUTPUT_CHARS": 12000,
    "TOOL_OUTPUT_PREVIEW_CHARS": 1200,
    "AUTO_COMPACT_TOKEN_THRESHOLD": 24000,
    "MAX_REACTIVE_COMPACT_RETRIES": 1,
    "MAX_SUMMARY_INPUT_CHARS": 30000,
    "MAX_OUTPUT_TOKENS": 2048,
    "ENABLE_SUBAGENT_LLM_COMPACT": False,
    "TRANSCRIPT_DIR": ".transcripts",
    "TOOL_OUTPUT_DIR": ".task_outputs/tool-results",
}


DEFAULT_MEMORY_CONFIG: Dict[str, Any] = {
    "ENABLE_MEMORY": True,
    "PRIVATE_MEMORY_DIR": ".memory/private",
    "TEAM_MEMORY_DIR": ".memory/team",
    "MAX_INDEX_LINES": 200,
    "MAX_MEMORY_FILES": 200,
    "MAX_RELEVANT_MEMORIES": 5,
    "MAX_MEMORY_FILE_CHARS": 4096,
    "MAX_TOTAL_MEMORY_CHARS": 60000,
    "AUTO_EXTRACT_MEMORY": True,
    "EXTRACT_RECENT_MESSAGES": 12,
    "MEMORY_RELEVANCE_MAX_TOKENS": 300,
    "MEMORY_EXTRACT_MAX_TOKENS": 1200,
    "MEMORY_LLM_TIMEOUT_SECONDS": 8,
    "DREAM_ENABLED": True,
    "DREAM_MIN_FILES": 10,
    "DREAM_MIN_INTERVAL_HOURS": 24,
    "MEMORY_LOCK_TTL_MINUTES": 60,
    "ALLOW_SUBAGENT_MEMORY_READ": True,
    "ALLOW_SUBAGENT_MEMORY_WRITE": False,
}


DEFAULT_PROMPT_CONFIG: Dict[str, Any] = {
    "ENABLE_PROMPT_CACHE": True,
    "INJECT_TOOL_SUMMARY": True,
    "INJECT_SKILL_CATALOG": True,
    "INJECT_MEMORY_INDEX": True,
    "INJECT_PROJECT_INSTRUCTIONS": True,
    "PROJECT_INSTRUCTION_FILES": ["CLAUDE.md", ".claude/CLAUDE.md", "AGENTS.md"],
    "MAX_PROJECT_INSTRUCTION_CHARS": 12000,
    "INJECT_RUNTIME_CONTEXT": True,
    "STATIC_DYNAMIC_BOUNDARY": "<SYSTEM_PROMPT_DYNAMIC_BOUNDARY>",
    "DEBUG_PROMPT_SECTIONS": False,
}


DEFAULT_RECOVERY_CONFIG: Dict[str, Any] = {
    "ENABLE_RECOVERY": True,
    "MAX_TRANSIENT_RETRIES": 3,
    "MAX_CONTEXT_RECOVERY_RETRIES": 1,
    "MAX_CONTINUATION_RETRIES": 2,
    "BACKOFF_BASE_SECONDS": 1,
    "BACKOFF_MAX_SECONDS": 20,
    "BACKOFF_JITTER_RATIO": 0.25,
    "FALLBACK_AFTER_OVERLOADS": 3,
    "FALLBACK_MODEL_ID": "",
    "RETRY_STATUS_CODES": [429, 500, 502, 503, 504, 529],
    "CONTEXT_ERROR_KEYWORDS": [
        "context length",
        "maximum context",
        "prompt too long",
        "too many tokens",
        "tokens exceed",
        "context_length_exceeded",
        "413",
    ],
    "TRANSIENT_ERROR_KEYWORDS": [
        "rate limit",
        "too many requests",
        "overloaded",
        "temporarily unavailable",
        "timeout",
        "timed out",
        "connection error",
        "connection reset",
    ],
}


DEFAULT_TASK_CONFIG: Dict[str, Any] = {
    "ENABLE_TASK_SYSTEM": True,
    "TASK_DIR": ".tasks",
    "TASK_ID_PREFIX": "task_",
    "ENABLE_TASK_LOCKS": True,
    "LOCK_TIMEOUT_SECONDS": 5,
    "MAX_TASKS_IN_LIST_OUTPUT": 50,
    "ALLOW_SUBAGENT_TASK_TOOLS": False,
    "REQUIRE_OWNER_TO_COMPLETE": True,
    "ENABLE_CYCLE_DETECTION": True,
}


DEFAULT_BACKGROUND_CONFIG: Dict[str, Any] = {
    "ENABLE_BACKGROUND_TASKS": True,
    "RUNTIME_TASK_DIR": ".runtime-tasks",
    "OUTPUT_DIR": ".runtime-tasks/outputs",
    "TASK_ID_PREFIX": "bg_",
    "MAX_NOTIFICATION_OUTPUT_CHARS": 1200,
    "MAX_BACKGROUND_TASKS_IN_LIST": 50,
    "DEFAULT_COMMAND_TIMEOUT_SECONDS": 0,
    "SLOW_COMMAND_KEYWORDS": [
        "npm install",
        "pip install",
        "pytest",
        "npm test",
        "npm run build",
        "docker build",
        "cargo build",
        "make",
    ],
}


DEFAULT_CRON_CONFIG: Dict[str, Any] = {
    "ENABLE_CRON_SCHEDULER": True,
    "CRON_TASK_DIR": ".runtime-tasks",
    "CRON_TASK_FILE": ".runtime-tasks/scheduled_tasks.json",
    "CRON_EVENT_FILE": ".runtime-tasks/scheduled_events.jsonl",
    "CRON_LOCK_FILE": ".runtime-tasks/scheduled.lock",
    "CRON_ID_PREFIX": "cron_",
    "CRON_SESSION_ID_PREFIX": "cron_session_",
    "CRON_EVENT_ID_PREFIX": "cron_evt_",
    "CHECK_INTERVAL_SECONDS": 1,
    "QUEUE_PROCESSOR_INTERVAL_SECONDS": 0.2,
    "MAX_CRON_JOBS": 50,
    "MAX_TRIGGERED_EVENTS_PER_TURN": 5,
    "ENABLE_DURABLE_CRON": True,
    "ENABLE_SESSION_CRON": True,
}


DEFAULT_TEAM_CONFIG: Dict[str, Any] = {
    "ENABLE_AGENT_TEAMS": True,
    "ENABLE_TEAM_PROTOCOLS": True,
    "ENABLE_AUTONOMOUS_AGENTS": True,
    "TEAM_DIR": ".team",
    "TEAM_INBOX_DIR": ".team/inbox",
    "TEAM_ID": "default",
    "LEAD_AGENT_NAME": "lead",
    "MAX_TEAMMATES": 5,
    "MAX_TEAMMATE_TURNS": 10,
    "TEAM_INBOX_POLL_SECONDS": 1,
    "MAX_INBOX_MESSAGES_PER_TURN": 20,
    "TEAMMATE_RESULT_MAX_CHARS": 6000,
    "TEAM_REQUEST_FILE": ".team/requests.json",
    "TEAM_REQUEST_ID_PREFIX": "team_req_",
    "TEAM_REQUEST_TIMEOUT_SECONDS": 300,
    "TEAM_IDLE_POLL_SECONDS": 1,
    "TEAM_IDLE_MAX_SECONDS": 0,
    "TEAM_IDLE_NOTIFY_LEAD": True,
    "PLAN_APPROVAL_REQUIRED": True,
    "PLAN_APPROVAL_MAX_CHARS": 6000,
    "AUTONOMOUS_TASK_SCAN_ENABLED": True,
    "AUTONOMOUS_IDLE_SCAN_SECONDS": 5,
    "AUTONOMOUS_IDLE_TIMEOUT_SECONDS": 60,
    "AUTONOMOUS_MAX_CLAIMS_PER_IDLE": 1,
    "AUTONOMOUS_EVENT_FILE": ".team/autonomous_events.jsonl",
    "AUTONOMOUS_REQUIRE_TASK_METADATA_MATCH": False,
    "AUTONOMOUS_ROLE_METADATA_KEY": "role",
    "AUTONOMOUS_NOTIFY_LEAD_ON_CLAIM": True,
    "AUTONOMOUS_NOTIFY_LEAD_ON_COMPLETE": True,
}


DEFAULT_WORKTREE_CONFIG: Dict[str, Any] = {
    "ENABLE_WORKTREE_ISOLATION": True,
    "WORKTREE_ROOT": ".worktrees",
    "WORKTREE_BRANCH_PREFIX": "wt/",
    "WORKTREE_INDEX_FILE": ".worktrees/index.json",
    "WORKTREE_EVENT_FILE": ".worktrees/events.jsonl",
    "WORKTREE_NAME_PATTERN": "^[A-Za-z0-9._-]{1,64}$",
    "WORKTREE_BASE_REF": "HEAD",
    "WORKTREE_ALLOW_CREATE_WITH_DIRTY_REPO": False,
    "WORKTREE_REMOVE_REQUIRES_CLEAN": True,
    "WORKTREE_BIND_METADATA_KEY": "worktree",
    "WORKTREE_AUTO_ENTER_ON_CLAIM": True,
    "WORKTREE_NOTIFY_LEAD_ON_BIND": True,
}


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value[0] == value[-1] and value.startswith(("'", '"')):
        return value[1:-1]
    if value == "[]":
        return []
    if value == "{}":
        return {}
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    try:
        return int(value)
    except ValueError:
        pass
    return value


def _next_meaningful_line(lines, start_index: int):
    for line in lines[start_index:]:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return line
    return ""


def _load_simple_yaml(text: str) -> Dict[str, Any]:
    """PyYAML 不可用时的兜底解析器，只覆盖本项目配置所需的基础 YAML。"""
    lines = text.splitlines()
    root: Dict[str, Any] = {}
    stack = [(-1, root)]

    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(line) - len(line.lstrip(" "))
        while stack and indent <= stack[-1][0]:
            stack.pop()

        container = stack[-1][1]
        if stripped.startswith("- "):
            if not isinstance(container, list):
                raise ValueError("YAML 列表格式错误")
            item_text = stripped[2:].strip()
            is_quoted = (
                len(item_text) >= 2
                and item_text[0] == item_text[-1]
                and item_text.startswith(("'", '"'))
            )
            if ":" in item_text and not is_quoted:
                key, raw_value = item_text.split(":", 1)
                item = {key.strip(): _parse_scalar(raw_value.strip())}
                container.append(item)
                stack.append((indent, item))
                continue
            container.append(_parse_scalar(item_text))
            continue

        if ":" not in stripped or not isinstance(container, dict):
            raise ValueError("YAML 对象格式错误")

        key, raw_value = stripped.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        if raw_value:
            container[key] = _parse_scalar(raw_value)
            continue

        next_line = _next_meaningful_line(lines, index + 1)
        next_stripped = next_line.strip()
        child = [] if next_stripped.startswith("- ") else {}
        container[key] = child
        stack.append((indent, child))

    return root


def _merge_config(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """递归合并配置，避免配置文件只写一部分时缺少默认字段。"""
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_config(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_yaml_config(config_file: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """读取项目内的 YAML 配置文件。"""
    config_path = safe_path(config_file)
    if not config_path.exists():
        return deepcopy(default or {})

    text = config_path.read_text(encoding="utf-8")
    if yaml is not None:
        data = yaml.safe_load(text) or {}
    else:
        data = _load_simple_yaml(text)

    if not isinstance(data, dict):
        raise ValueError(f"配置文件必须是 YAML 对象: {config_file}")
    return data


def load_permission_config(config_file: str = "configs/permission_config.yml") -> Dict[str, Any]:
    """加载权限配置，并补齐默认值。"""
    data = load_yaml_config(config_file, DEFAULT_PERMISSION_CONFIG)
    return _merge_config(DEFAULT_PERMISSION_CONFIG, data)


def load_hooks_config(config_file: str = "configs/hooks_config.yml") -> Dict[str, Any]:
    """加载 Hook 配置，并补齐默认值。"""
    data = load_yaml_config(config_file, DEFAULT_HOOKS_CONFIG)
    return _merge_config(DEFAULT_HOOKS_CONFIG, data)


def load_todo_config(config_file: str = "configs/todo_config.yml") -> Dict[str, Any]:
    """加载 TodoWrite 配置，并补齐默认值。"""
    data = load_yaml_config(config_file, DEFAULT_TODO_CONFIG)
    return _merge_config(DEFAULT_TODO_CONFIG, data)


def load_subagent_config(config_file: str = "configs/subagent_config.yml") -> Dict[str, Any]:
    """加载 Subagent 配置，并补齐默认值。"""
    data = load_yaml_config(config_file, DEFAULT_SUBAGENT_CONFIG)
    return _merge_config(DEFAULT_SUBAGENT_CONFIG, data)


def load_skill_config(config_file: str = "configs/skill_config.yml") -> Dict[str, Any]:
    """加载 Skill Loading 配置，并补齐默认值。"""
    data = load_yaml_config(config_file, DEFAULT_SKILL_CONFIG)
    return _merge_config(DEFAULT_SKILL_CONFIG, data)


def load_compact_config(config_file: str = "configs/compact_config.yml") -> Dict[str, Any]:
    """加载 Context Compact 配置，并补齐默认值。"""
    data = load_yaml_config(config_file, DEFAULT_COMPACT_CONFIG)
    return _merge_config(DEFAULT_COMPACT_CONFIG, data)


def load_memory_config(config_file: str = "configs/memory_config.yml") -> Dict[str, Any]:
    """加载长期 Memory 配置，并补齐默认值。"""
    data = load_yaml_config(config_file, DEFAULT_MEMORY_CONFIG)
    return _merge_config(DEFAULT_MEMORY_CONFIG, data)


def load_prompt_config(config_file: str = "configs/prompt_config.yml") -> Dict[str, Any]:
    """加载 System Prompt 配置，并补齐默认值。"""
    data = load_yaml_config(config_file, DEFAULT_PROMPT_CONFIG)
    return _merge_config(DEFAULT_PROMPT_CONFIG, data)


def load_recovery_config(config_file: str = "configs/recovery_config.yml") -> Dict[str, Any]:
    """加载 Error Recovery 配置，并补齐默认值。"""
    data = load_yaml_config(config_file, DEFAULT_RECOVERY_CONFIG)
    return _merge_config(DEFAULT_RECOVERY_CONFIG, data)


def load_task_config(config_file: str = "configs/task_config.yml") -> Dict[str, Any]:
    """加载 Task System 配置，并补齐默认值。"""
    data = load_yaml_config(config_file, DEFAULT_TASK_CONFIG)
    return _merge_config(DEFAULT_TASK_CONFIG, data)


def load_background_config(config_file: str = "configs/background_config.yml") -> Dict[str, Any]:
    """加载 Background Tasks 配置，并补齐默认值。"""
    data = load_yaml_config(config_file, DEFAULT_BACKGROUND_CONFIG)
    return _merge_config(DEFAULT_BACKGROUND_CONFIG, data)


def load_cron_config(config_file: str = "configs/cron_config.yml") -> Dict[str, Any]:
    """加载 Cron Scheduler 配置，并补齐默认值。"""
    data = load_yaml_config(config_file, DEFAULT_CRON_CONFIG)
    return _merge_config(DEFAULT_CRON_CONFIG, data)


def load_team_config(config_file: str = "configs/team_config.yml") -> Dict[str, Any]:
    """加载 Agent Teams 配置，并补齐默认值。"""
    data = load_yaml_config(config_file, DEFAULT_TEAM_CONFIG)
    return _merge_config(DEFAULT_TEAM_CONFIG, data)


def load_worktree_config(config_file: str = "configs/worktree_config.yml") -> Dict[str, Any]:
    """加载 Worktree Isolation 配置，并补齐默认值。"""
    data = load_yaml_config(config_file, DEFAULT_WORKTREE_CONFIG)
    return _merge_config(DEFAULT_WORKTREE_CONFIG, data)


permission_config = load_permission_config()
hooks_config = load_hooks_config()
todo_config = load_todo_config()
subagent_config = load_subagent_config()
skill_config = load_skill_config()
compact_config = load_compact_config()
memory_config = load_memory_config()
prompt_config = load_prompt_config()
recovery_config = load_recovery_config()
task_config = load_task_config()
background_config = load_background_config()
cron_config = load_cron_config()
team_config = load_team_config()
worktree_config = load_worktree_config()
