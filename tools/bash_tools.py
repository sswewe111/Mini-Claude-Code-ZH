import platform
import subprocess
from pathlib import Path

from utils.logger_handler import logger


def _shell_command(command: str) -> tuple:
    system = platform.system().lower()
    if system == "windows":
        return "powershell", ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command]
    if system in ("linux", "darwin"):
        return "bash", ["bash", "-lc", command]
    return "system-shell", [command]


def run_bash(command: str, cwd: str = None) -> str:
    """根据当前系统选择 PowerShell 或 bash 执行命令。"""
    shell_name, command_args = _shell_command(command)
    try:
        result = subprocess.run(
            command_args,
            shell=False,
            cwd=Path(cwd).resolve() if cwd else Path.cwd(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        logger.error("%s 命令超时: %s", shell_name, command)
        return "Error: command timed out after 120 seconds"
    except OSError as exc:
        logger.exception("%s 命令执行失败", shell_name)
        return f"Error: {exc}"

    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    parts = [f"shell: {shell_name}", f"exit_code: {result.returncode}"]
    if stdout:
        parts.append(f"stdout:\n{stdout}")
    if stderr:
        parts.append(f"stderr:\n{stderr}")
    if len(parts) == 2:
        parts.append("output: (no output)")
    return "\n\n".join(parts)
