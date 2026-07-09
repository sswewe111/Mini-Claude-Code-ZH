from pathlib import Path


WORKDIR = Path.cwd().resolve()


def safe_path(path: str) -> Path:
    """把输入路径限制在当前工作区内，防止工具越界读写。"""
    resolved = (WORKDIR / path).resolve()
    try:
        resolved.relative_to(WORKDIR)
    except ValueError as exc:
        raise ValueError(f"Path escapes workspace: {path}") from exc
    return resolved


def safe_path_under(root: Path, path: str) -> Path:
    """Resolve a user path under an explicit sandbox root."""
    root = Path(root).resolve()
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Path escapes sandbox root: {path}") from exc
    return resolved
