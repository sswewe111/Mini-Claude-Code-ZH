import json
from datetime import datetime
from typing import Callable, Dict, List

from managers.memory_manager import MEMORY_MANAGER
from managers.skill_manager import SKILL_REGISTRY
from prompts.background_prompts import BACKGROUND_SYSTEM_RULES
from prompts.cron_prompts import CRON_SYSTEM_RULES
from prompts.memory_prompts import MEMORY_READ_ONLY_RULES, MEMORY_SYSTEM_RULES
from prompts.task_prompts import TASK_SYSTEM_RULES
from prompts.team_prompts import TEAM_SYSTEM_RULES, TEAMMATE_SYSTEM_RULES
from prompts.prompt_sections import (
    MAIN_IDENTITY_SECTION,
    MAIN_SECTION_ORDER,
    PERMISSION_RULES_SECTION,
    PLANNING_RULES_SECTION,
    RESPONSE_STYLE_SECTION,
    STATIC_SECTIONS,
    SUBAGENT_CONTEXT_RULES_SECTION,
    SUBAGENT_IDENTITY_SECTION,
    SUBAGENT_RESULT_RULES_SECTION,
    SUBAGENT_SECTION_ORDER,
    TEAMMATE_IDENTITY_SECTION,
    TEAMMATE_SECTION_ORDER,
    TOOL_RULES_SECTION,
)
from state.prompt_state import PromptBuildResult, PromptSection, SystemPromptContext
from tools_configs import BASE_TOOLS
from utils.config_handler import background_config, cron_config, memory_config, prompt_config, skill_config, task_config, team_config
from utils.logger_handler import logger
from utils.path_sandbox import safe_path


_PROMPT_CACHE_KEY = ""
_PROMPT_CACHE_TEXT = ""


def _tool_names(tool_defs=None) -> List[str]:
    tool_defs = tool_defs or BASE_TOOLS
    names = []
    for tool in tool_defs:
        name = tool.get("function", {}).get("name", "")
        if name:
            names.append(name)
    return names


def _tool_summary(context: SystemPromptContext) -> str:
    if not prompt_config.get("INJECT_TOOL_SUMMARY", True):
        return ""
    enabled = set(context.enabled_tools)
    lines = ["可用工具摘要："]
    for tool in BASE_TOOLS:
        function = tool.get("function", {})
        name = function.get("name", "")
        description = function.get("description", "")
        if name and (not enabled or name in enabled):
            lines.append(f"- {name}: {description}")
    return "\n".join(lines)


def _skill_catalog_prompt() -> str:
    if not prompt_config.get("INJECT_SKILL_CATALOG", True):
        return ""
    if not skill_config.get("INJECT_SKILL_CATALOG", True):
        return ""
    return (
        "可用技能目录：\n"
        f"{SKILL_REGISTRY.list_catalog()}\n\n"
        "如果任务需要某个技能的完整说明，先调用 load_skill(name)。"
        "不要在未加载技能正文时编造技能细节。"
    )


def _memory_index_prompt(agent_type: str) -> str:
    if not prompt_config.get("INJECT_MEMORY_INDEX", True):
        return ""
    if not memory_config.get("ENABLE_MEMORY", True):
        return ""
    index = MEMORY_MANAGER.load_index_prompt()
    if not index:
        return ""
    rules = MEMORY_READ_ONLY_RULES if agent_type == "subagent" else MEMORY_SYSTEM_RULES
    return (
        "长期记忆索引：\n"
        f"{rules}\n\n"
        f"{index}\n\n"
        "如果当前任务和某条记忆相关，优先使用已注入的 Memory context；"
        "如果记忆涉及当前文件、函数或配置，先以当前项目状态验证。"
    )


def _task_rules_prompt(agent_type: str) -> str:
    if not task_config.get("ENABLE_TASK_SYSTEM", True):
        return ""
    if agent_type == "subagent" and not task_config.get("ALLOW_SUBAGENT_TASK_TOOLS", False):
        return ""
    return TASK_SYSTEM_RULES


def _background_rules_prompt(agent_type: str) -> str:
    if not background_config.get("ENABLE_BACKGROUND_TASKS", True):
        return ""
    if agent_type == "subagent":
        return ""
    return BACKGROUND_SYSTEM_RULES


def _cron_rules_prompt(agent_type: str) -> str:
    if not cron_config.get("ENABLE_CRON_SCHEDULER", True):
        return ""
    if agent_type == "subagent":
        return ""
    return CRON_SYSTEM_RULES


def _team_rules_prompt(agent_type: str) -> str:
    if not team_config.get("ENABLE_AGENT_TEAMS", True):
        return ""
    if agent_type == "subagent":
        return ""
    if agent_type == "teammate":
        return TEAMMATE_SYSTEM_RULES
    return TEAM_SYSTEM_RULES


def _project_instructions() -> str:
    if not prompt_config.get("INJECT_PROJECT_INSTRUCTIONS", True):
        return ""
    max_chars = int(prompt_config.get("MAX_PROJECT_INSTRUCTION_CHARS", 12000))
    chunks = []
    total = 0
    for file_name in prompt_config.get("PROJECT_INSTRUCTION_FILES", []):
        path = safe_path(file_name)
        if not path.exists() or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")[: max_chars - total]
        if not text.strip():
            continue
        chunks.append(f"## {file_name}\n{text.strip()}")
        total += len(text)
        if total >= max_chars:
            break
    if not chunks:
        return ""
    return "项目指令文件：\n" + "\n\n".join(chunks)


def _runtime_context(context: SystemPromptContext) -> str:
    if not prompt_config.get("INJECT_RUNTIME_CONTEXT", True):
        return ""
    lines = [
        "运行时上下文：",
        f"- 当前日期时间：{datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- Agent 类型：{context.agent_type}",
    ]
    for key, value in sorted(context.runtime_context.items()):
        if value in ("", None, [], {}):
            continue
        lines.append(f"- {key}: {value}")
    return "\n".join(lines)


def _workspace_section(context: SystemPromptContext) -> str:
    return f"当前工作目录：{context.workdir}"


def _section_builders(context: SystemPromptContext) -> Dict[str, Callable[[], str]]:
    return {
        "identity": lambda: MAIN_IDENTITY_SECTION,
        "subagent_identity": lambda: SUBAGENT_IDENTITY_SECTION,
        "teammate_identity": lambda: TEAMMATE_IDENTITY_SECTION,
        "workspace": lambda: _workspace_section(context),
        "subagent_context_rules": lambda: SUBAGENT_CONTEXT_RULES_SECTION,
        "tool_rules": lambda: TOOL_RULES_SECTION,
        "tool_summary": lambda: _tool_summary(context),
        "planning_rules": lambda: PLANNING_RULES_SECTION,
        "task_rules": lambda: _task_rules_prompt(context.agent_type),
        "background_rules": lambda: _background_rules_prompt(context.agent_type),
        "cron_rules": lambda: _cron_rules_prompt(context.agent_type),
        "team_rules": lambda: _team_rules_prompt(context.agent_type),
        "permission_rules": lambda: PERMISSION_RULES_SECTION,
        "skills_index": _skill_catalog_prompt,
        "memory_rules_and_index": lambda: _memory_index_prompt(context.agent_type),
        "project_instructions": _project_instructions,
        "runtime_context": lambda: _runtime_context(context),
        "response_style": lambda: RESPONSE_STYLE_SECTION,
        "subagent_result_rules": lambda: SUBAGENT_RESULT_RULES_SECTION,
    }


def _build_sections(context: SystemPromptContext) -> List[PromptSection]:
    if context.agent_type == "subagent":
        order = SUBAGENT_SECTION_ORDER
    elif context.agent_type == "teammate":
        order = TEAMMATE_SECTION_ORDER
    else:
        order = MAIN_SECTION_ORDER
    builders = _section_builders(context)
    sections: List[PromptSection] = []
    for name in order:
        builder = builders.get(name)
        if not builder:
            continue
        content = builder().strip()
        if not content:
            continue
        sections.append(
            PromptSection(
                name=name,
                content=content,
                dynamic=name not in STATIC_SECTIONS,
            )
        )
    return sections


def _cache_key(context: SystemPromptContext) -> str:
    payload = {
        "workdir": context.workdir,
        "agent_type": context.agent_type,
        "enabled_tools": context.enabled_tools,
        "runtime_context": context.runtime_context,
        "tool_names": context.enabled_tools,
        "skill_catalog": SKILL_REGISTRY.list_catalog() if skill_config.get("INJECT_SKILL_CATALOG", True) else "",
        "memory_index": MEMORY_MANAGER.load_index_prompt() if memory_config.get("ENABLE_MEMORY", True) else "",
        "project_instructions": _project_instructions(),
        "prompt_config": prompt_config,
        "task_config": task_config,
        "background_config": background_config,
        "cron_config": cron_config,
        "team_config": team_config,
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)


def _assemble_text(sections: List[PromptSection]) -> str:
    boundary = str(prompt_config.get("STATIC_DYNAMIC_BOUNDARY", "<SYSTEM_PROMPT_DYNAMIC_BOUNDARY>"))
    static_sections = [section.content for section in sections if not section.dynamic]
    dynamic_sections = [section.content for section in sections if section.dynamic]
    parts = []
    if static_sections:
        parts.append("\n\n".join(static_sections))
    if dynamic_sections:
        if boundary:
            parts.append(boundary)
        parts.append("\n\n".join(dynamic_sections))
    return "\n\n".join(parts)


def assemble_system_prompt(context: SystemPromptContext) -> PromptBuildResult:
    """按 section profile 组装 system prompt，不使用缓存。"""
    sections = _build_sections(context)
    text = _assemble_text(sections)
    section_names = [section.name for section in sections]
    if prompt_config.get("DEBUG_PROMPT_SECTIONS", False):
        logger.info("System prompt sections: %s", section_names)
    return PromptBuildResult(text=text, section_names=section_names, cache_hit=False)


def get_system_prompt(context: SystemPromptContext) -> str:
    """获取 system prompt；context 未变化时复用上一次字符串。"""
    global _PROMPT_CACHE_KEY, _PROMPT_CACHE_TEXT
    if prompt_config.get("ENABLE_PROMPT_CACHE", True):
        key = _cache_key(context)
        if key == _PROMPT_CACHE_KEY and _PROMPT_CACHE_TEXT:
            if prompt_config.get("DEBUG_PROMPT_SECTIONS", False):
                logger.info("System prompt cache hit: agent_type=%s", context.agent_type)
            return _PROMPT_CACHE_TEXT
        result = assemble_system_prompt(context)
        _PROMPT_CACHE_KEY = key
        _PROMPT_CACHE_TEXT = result.text
        return result.text

    return assemble_system_prompt(context).text


def build_main_system_prompt(workdir: str, runtime_context: dict = None) -> str:
    """主 Agent 的 system prompt：运行时按 section 组装。"""
    context = SystemPromptContext(
        workdir=workdir,
        agent_type="main",
        enabled_tools=_tool_names(),
        runtime_context=runtime_context or {},
    )
    return get_system_prompt(context)


def build_subagent_system_prompt(workdir: str, runtime_context: dict = None) -> str:
    """子 Agent 的 system prompt：使用子 Agent profile 组装。"""
    from tools_configs.subagent_configs import SUBAGENT_AVAILABLE_TOOLS

    context = SystemPromptContext(
        workdir=workdir,
        agent_type="subagent",
        enabled_tools=_tool_names(SUBAGENT_AVAILABLE_TOOLS),
        runtime_context=runtime_context or {},
    )
    return get_system_prompt(context)


def build_teammate_system_prompt(workdir: str, runtime_context: dict = None) -> str:
    """teammate 的 system prompt：使用团队 profile 组装。"""
    from tools_configs.team_configs import TEAMMATE_AVAILABLE_TOOLS

    context = SystemPromptContext(
        workdir=workdir,
        agent_type="teammate",
        enabled_tools=_tool_names(TEAMMATE_AVAILABLE_TOOLS),
        runtime_context=runtime_context or {},
    )
    return get_system_prompt(context)
