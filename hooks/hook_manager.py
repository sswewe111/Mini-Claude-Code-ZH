import json
import os
import subprocess
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from hooks import builtin_hooks
from state.hook_state import HookContext, HookResult
from utils.config_handler import hooks_config
from utils.logger_handler import logger


HookCallback = Callable[[HookContext], Optional[object]]
HOOK_EVENTS = (
    "SessionStart",
    "BeforeModelCall",
    "AfterModelCall",
    "PreToolUse",
    "PostToolUse",
    "Stop",
)


class HookManager:
    """管理 Python 内置 hook 和配置命令 hook。"""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or hooks_config
        self.callbacks: Dict[str, List[Tuple[str, str, HookCallback]]] = {
            event: [] for event in HOOK_EVENTS
        }
        self.final_callbacks: Dict[str, List[Tuple[str, str, HookCallback]]] = {
            event: [] for event in HOOK_EVENTS
        }

    def register(
        self,
        event: str,
        callback: HookCallback,
        matcher: str = "*",
        name: Optional[str] = None,
        final: bool = False,
    ) -> None:
        if event not in self.callbacks:
            raise ValueError(f"Unknown hook event: {event}")
        target = self.final_callbacks if final else self.callbacks
        target[event].append((matcher, name or callback.__name__, callback))

    def register_builtin_hooks(self) -> None:
        self.register("SessionStart", builtin_hooks.log_session_start)
        self.register("SessionStart", builtin_hooks.memory_session_start_hook)
        self.register("SessionStart", builtin_hooks.cron_session_start_hook)
        self.register("SessionStart", builtin_hooks.team_session_start_hook)
        self.register("SessionStart", builtin_hooks.worktree_session_start_hook)
        self.register("BeforeModelCall", builtin_hooks.memory_before_model_call_hook)
        self.register("BeforeModelCall", builtin_hooks.background_before_model_call_hook)
        self.register("BeforeModelCall", builtin_hooks.team_before_model_call_hook)
        self.register("BeforeModelCall", builtin_hooks.todo_reminder_hook)
        self.register("BeforeModelCall", builtin_hooks.compact_before_model_call_hook)
        self.register("BeforeModelCall", builtin_hooks.log_before_model_call)
        self.register("AfterModelCall", builtin_hooks.log_after_model_call)
        self.register("AfterModelCall", builtin_hooks.todo_round_tracker_hook)
        self.register("PreToolUse", builtin_hooks.log_pre_tool_use)
        self.register("PreToolUse", builtin_hooks.permission_check_hook, final=True)
        self.register("PostToolUse", builtin_hooks.log_post_tool_use)
        self.register("PostToolUse", builtin_hooks.compact_post_tool_use_hook)
        self.register("Stop", builtin_hooks.memory_stop_extract_hook)

    def run_hooks(self, event: str, context: Optional[HookContext] = None) -> HookResult:
        context = context or HookContext(event=event)
        context.event = event
        result = HookResult()

        for matcher, name, callback in self.callbacks.get(event, []):
            if not self._matches(matcher, context):
                continue
            self._run_python_hook(name, callback, context, result)
            self._apply_result_updates_to_context(context, result)
            if result.blocked:
                return result

        self._run_command_hooks(event, context, result)
        if result.blocked:
            return result

        for matcher, name, callback in self.final_callbacks.get(event, []):
            if not self._matches(matcher, context):
                continue
            self._run_python_hook(name, callback, context, result)
            self._apply_result_updates_to_context(context, result)
            if result.blocked:
                return result
        return result

    def _matches(self, matcher: str, context: HookContext) -> bool:
        return matcher == "*" or matcher == (context.tool_name or "")

    def _run_python_hook(
        self,
        name: str,
        callback: HookCallback,
        context: HookContext,
        result: HookResult,
    ) -> None:
        try:
            hook_output = callback(context)
            self._merge_output(name, hook_output, result)
        except Exception as exc:
            message = f"python hook {name} failed: {exc}"
            logger.exception(message)
            result.errors.append(message)

    def _run_command_hooks(
        self,
        event: str,
        context: HookContext,
        result: HookResult,
    ) -> None:
        if not self.config.get("enabled", False):
            return
        if not self._workspace_trusted():
            logger.info("[hook:%s] 外部命令 hook 未运行：工作区未信任", event)
            return

        event_hooks = self.config.get("events", {}).get(event, [])
        if not isinstance(event_hooks, list):
            return

        for hook_def in event_hooks:
            if not isinstance(hook_def, dict) or not hook_def.get("enabled", True):
                continue
            matcher = hook_def.get("matcher", "*")
            if not self._matches(matcher, context):
                continue

            command = hook_def.get("command", "")
            if not command:
                continue

            self._run_command_hook(event, hook_def.get("name", command), command, context, result)
            self._apply_result_updates_to_context(context, result)
            if result.blocked:
                return

    def _apply_result_updates_to_context(self, context: HookContext, result: HookResult) -> None:
        if result.updated_output is not None:
            context.tool_output = result.updated_output

    def _workspace_trusted(self) -> bool:
        trust = self.config.get("trust", {})
        if not trust.get("require_marker", False):
            return True
        marker = Path.cwd() / trust.get("marker_path", ".mini_claude_code_trusted")
        return marker.exists()

    def _run_command_hook(
        self,
        event: str,
        name: str,
        command: str,
        context: HookContext,
        result: HookResult,
    ) -> None:
        env = dict(os.environ)
        env["HOOK_EVENT"] = event
        env["HOOK_TOOL_NAME"] = context.tool_name or ""
        env["HOOK_TOOL_INPUT"] = json.dumps(context.tool_input, ensure_ascii=False)[:10000]
        env["HOOK_TOOL_OUTPUT"] = (context.tool_output or "")[:10000]

        timeout = int(self.config.get("timeout_seconds", 30))
        try:
            completed = subprocess.run(
                command,
                shell=True,
                cwd=Path.cwd(),
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            message = f"command hook {name} timeout after {timeout}s"
            logger.warning("[hook:%s] %s", event, message)
            result.errors.append(message)
            return
        except OSError as exc:
            message = f"command hook {name} failed: {exc}"
            logger.exception("[hook:%s] %s", event, message)
            result.errors.append(message)
            return

        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        if completed.returncode == 0:
            if stdout:
                self._merge_json_stdout(name, stdout, result)
            return
        if completed.returncode == 1:
            result.blocked = True
            result.block_reason = stderr or f"blocked by hook {name}"
            logger.warning("[hook:%s] BLOCKED: %s", event, result.block_reason)
            return
        if completed.returncode == 2:
            if stderr:
                logger.info("[hook:%s] %s: %s", event, name, stderr[:200])
            return

        message = f"command hook {name} exit code {completed.returncode}: {stderr}"
        logger.warning("[hook:%s] %s", event, message)
        result.errors.append(message)

    def _merge_output(self, name: str, hook_output: object, result: HookResult) -> None:
        if hook_output is None:
            return
        if isinstance(hook_output, HookResult):
            self._merge_result(hook_output, result)
            return
        if isinstance(hook_output, dict):
            self._merge_dict(hook_output, result)
            return
        if isinstance(hook_output, str):
            logger.info("[hook] %s: %s", name, hook_output[:200])
            return
        result.errors.append(f"python hook {name} returned unsupported type")

    def _merge_json_stdout(self, name: str, stdout: str, result: HookResult) -> None:
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            logger.info("[hook] %s: %s", name, stdout[:200])
            return
        if isinstance(data, dict):
            self._merge_dict(data, result)

    def _merge_dict(self, data: dict, result: HookResult) -> None:
        if data.get("blocked"):
            result.blocked = True
            result.block_reason = data.get("block_reason") or data.get("blockReason") or "blocked by hook"
        updated_output = data.get("updated_output") or data.get("updatedOutput")
        if isinstance(updated_output, str):
            result.updated_output = updated_output
        message = data.get("message") or data.get("additionalContext")
        if message:
            logger.info("[hook] %s", str(message)[:200])

    def _merge_result(self, source: HookResult, target: HookResult) -> None:
        if source.blocked:
            target.blocked = True
            target.block_reason = source.block_reason
        if source.updated_output is not None:
            target.updated_output = source.updated_output
        target.errors.extend(source.errors)


_DEFAULT_HOOK_MANAGER: Optional[HookManager] = None


def get_default_hook_manager() -> HookManager:
    global _DEFAULT_HOOK_MANAGER
    if _DEFAULT_HOOK_MANAGER is None:
        manager = HookManager()
        manager.register_builtin_hooks()
        _DEFAULT_HOOK_MANAGER = manager
    return _DEFAULT_HOOK_MANAGER
