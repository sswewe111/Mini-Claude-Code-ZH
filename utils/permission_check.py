import json
import re
from typing import Any, Dict, Iterable, Optional

from utils.config_handler import permission_config
from utils.path_sandbox import safe_path
from state.permission_state import PermissionResult


def _as_set(value: Iterable[str]) -> set:
    return {item for item in value if item}


def _contains_dangerous_keyword(command: str, keywords: Iterable[str]) -> Optional[str]:
    """按命令词边界识别危险命令，避免只匹配某一种参数组合。"""
    command_lower = command.lower()
    for keyword in keywords:
        keyword_lower = keyword.lower()
        if re.fullmatch(r"[\w-]+", keyword_lower):
            pattern = rf"(?<![\w-]){re.escape(keyword_lower)}(?![\w-])"
            if re.search(pattern, command_lower):
                return keyword
            continue

        if keyword_lower in command_lower:
            return keyword
    return None


def request_user_approval(tool_name: str, args: Dict[str, Any], reason: str) -> bool:
    """交互式审批。EOF 或中断时默认拒绝。"""
    preview = json.dumps(args, ensure_ascii=False)
    if len(preview) > 300:
        preview = preview[:300] + "..."

    print("\n[Permission] 工具调用需要审批")
    print(f"工具: {tool_name}")
    print(f"原因: {reason}")
    print(f"参数: {preview}")
    try:
        answer = input("是否允许执行? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return answer in ("y", "yes")


def _approval_result(
    tool_name: str,
    args: Dict[str, Any],
    reason: str,
    approval: Dict[str, Any],
) -> PermissionResult:
    """根据审批模式返回结果；默认 ask 会暂停等待用户确认。"""
    approval_mode = approval.get("mode", "ask")
    if approval_mode == "auto_allow":
        return PermissionResult(True, reason, needs_approval=True)
    if approval_mode == "auto_deny":
        return PermissionResult(False, reason, needs_approval=True)
    if request_user_approval(tool_name, args, reason):
        return PermissionResult(True, reason, needs_approval=True)
    return PermissionResult(False, "user denied permission", needs_approval=True)


def check_permission(
    tool_name: str,
    args: Dict[str, Any],
    config: Optional[Dict[str, Any]] = None,
) -> PermissionResult:
    """
    按三道闸门检查工具权限。

    闸门 1：拒绝列表。命中 deny 工具或危险命令关键字时立即拒绝。
    闸门 2：规则匹配。检查工具是否在 allow 列表内；读文件在项目内直接允许。
    闸门 3：用户审批。项目外读取、写入文件、编辑文件都需要用户明确允许。
    """
    active_config = config or permission_config
    tools = active_config.get("tools", {})
    allow_tools = _as_set(tools.get("allow", []))
    deny_tools = _as_set(tools.get("deny", []))
    approval = active_config.get("approval", {})

    # 闸门 1：deny 永远优先。即使工具也写在 allow 里，只要出现在 deny 中就拒绝。
    if tool_name in deny_tools:
        return PermissionResult(False, f"tool denied by config: {tool_name}")

    # 闸门 1 的 bash 特化检查：危险命令关键字直接拒绝，不进入用户审批。
    if tool_name == "bash":
        command = args.get("command", "")
        keyword = _contains_dangerous_keyword(
            command,
            active_config.get("dangerous_commands", []),
        )
        if keyword:
            return PermissionResult(False, f"dangerous command keyword: {keyword}")

    # 闸门 2：allow 是当前 Agent 能力边界，未登记的工具不允许被模型调用。
    if allow_tools and tool_name not in allow_tools:
        return PermissionResult(False, f"tool not in allow list: {tool_name}")

    # 闸门 2：读文件只判断是否在当前项目内；项目内读取直接允许。
    if tool_name == "read_file":
        path = args.get("path")
        if not path:
            return PermissionResult(False, "read_file requires path")
        try:
            safe_path(path)
            return PermissionResult(True, "read path inside project")
        except ValueError:
            # 闸门 3：项目外读取不直接拒绝，交给用户审批。
            return _approval_result(
                tool_name,
                args,
                f"read path outside project: {path}",
                approval,
            )

    # 闸门 3：写入和编辑风险更高，不再按路径规则细分，统一询问用户。
    if tool_name in ("write_file", "edit_file"):
        path = args.get("path")
        if not path:
            return PermissionResult(False, f"{tool_name} requires path")
        return _approval_result(
            tool_name,
            args,
            f"{tool_name} requires user approval: {path}",
            approval,
        )

    required_tools = _as_set(approval.get("required_tools", []))
    # 闸门 3：命中 required_tools 的工具需要审批；测试时可用 auto_allow/auto_deny 避免交互阻塞。
    if tool_name in required_tools:
        reason = f"tool requires approval: {tool_name}"
        return _approval_result(tool_name, args, reason, approval)

    return PermissionResult(True, "permission allowed")
