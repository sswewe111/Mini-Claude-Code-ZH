from typing import Optional
from pathlib import Path

from utils.logger_handler import logger
from utils.path_sandbox import safe_path, safe_path_under


def _resolve_path(path: str, base_dir: Optional[str] = None):
    if base_dir:
        return safe_path_under(Path(base_dir), path)
    return safe_path(path)


def read_file(path: str, limit: Optional[int] = None, base_dir: Optional[str] = None) -> str:
    """读取文件前先经过路径沙箱，避免访问工作区外文件。"""
    logger.info("读取文件: %s", path)
    file_path = _resolve_path(path, base_dir)
    text = file_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if limit is not None and limit > 0 and len(lines) > limit:
        lines = lines[:limit] + [f"... ({len(lines) - limit} more lines)"]
    return "\n".join(lines)


def write_file(path: str, content: str, base_dir: Optional[str] = None) -> str:
    """写入文件前先解析安全路径，并自动创建父目录。"""
    logger.info("写入文件: %s", path)
    file_path = _resolve_path(path, base_dir)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} characters to {path}"


def edit_file(path: str, old_text: str, new_text: str, base_dir: Optional[str] = None) -> str:
    """只做精确替换，避免模型猜测导致误改。"""
    logger.info("编辑文件: %s", path)
    file_path = _resolve_path(path, base_dir)
    content = file_path.read_text(encoding="utf-8")
    if old_text not in content:
        logger.warning("编辑失败，old_text 未匹配: %s", path)
        return f"Error: old_text not found in {path}"
    file_path.write_text(content.replace(old_text, new_text, 1), encoding="utf-8")
    return f"Edited {path}"
