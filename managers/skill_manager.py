from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml
except ModuleNotFoundError:
    yaml = None

from state.skill_state import SkillManifest
from utils.config_handler import skill_config
from utils.logger_handler import logger
from utils.path_sandbox import WORKDIR, safe_path


def _clip(text: str, max_chars: int) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


def _parse_frontmatter(text: str) -> Tuple[Dict[str, Any], str]:
    """解析 SKILL.md 顶部 frontmatter；解析失败时回退为空元数据。"""
    if not text.startswith("---"):
        return {}, text

    lines = text.splitlines()
    end_index: Optional[int] = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_index = index
            break

    if end_index is None:
        return {}, text

    raw_meta = "\n".join(lines[1:end_index])
    body = "\n".join(lines[end_index + 1 :])
    if yaml is not None:
        try:
            data = yaml.safe_load(raw_meta) or {}
            return data if isinstance(data, dict) else {}, body
        except Exception:
            logger.exception("解析技能 frontmatter 失败，使用兜底解析")

    return _parse_simple_frontmatter(raw_meta), body


def _parse_simple_frontmatter(raw_meta: str) -> Dict[str, Any]:
    """PyYAML 不可用时的简单解析，覆盖 name/description 等常见字段。"""
    result: Dict[str, Any] = {}
    current_key: Optional[str] = None
    for line in raw_meta.splitlines():
        if not line.strip():
            continue
        if line.startswith((" ", "\t")) and current_key:
            result[current_key] = f"{result.get(current_key, '')} {line.strip()}".strip()
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        current_key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value.startswith(("'", '"')):
            value = value[1:-1]
        result[current_key] = value
    return result


class SkillRegistry:
    """扫描技能目录，并在模型按需请求时加载完整技能说明。"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.manifests: Dict[str, SkillManifest] = {}

    @property
    def skills_root(self) -> Path:
        return safe_path(self.config.get("SKILLS_ROOT", "skills"))

    @property
    def entry_name(self) -> str:
        return self.config.get("SKILL_ENTRY_FILE", "SKILL.md")

    def scan_skills(self) -> None:
        self.manifests = {}
        root = self.skills_root
        if not root.exists():
            logger.warning("技能目录不存在: %s", root)
            return

        for skill_dir in sorted(root.iterdir()):
            if not skill_dir.is_dir():
                continue
            entry_file = skill_dir / self.entry_name
            if not entry_file.exists():
                continue
            manifest = self._read_manifest(skill_dir, entry_file)
            if not manifest:
                continue
            if manifest.name in self.manifests:
                logger.warning("发现重复技能名，已跳过: %s", manifest.name)
                continue
            self.manifests[manifest.name] = manifest

        logger.info("技能目录扫描完成: count=%s", len(self.manifests))

    def _read_manifest(self, skill_dir: Path, entry_file: Path) -> Optional[SkillManifest]:
        try:
            text = entry_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = entry_file.read_text(encoding="utf-8-sig")
        except Exception:
            logger.exception("读取技能入口失败: %s", entry_file)
            return None

        meta, body = _parse_frontmatter(text)
        name = str(meta.get("name") or skill_dir.name).strip()
        description = meta.get("description") or _first_heading_or_line(body)
        description = _clip(str(description), int(self.config.get("MAX_SKILL_DESCRIPTION_CHARS", 180)))
        if not name:
            logger.warning("技能入口缺少 name，已跳过: %s", entry_file)
            return None
        return SkillManifest(
            name=name,
            description=description,
            path=skill_dir,
            entry_file=entry_file,
        )

    def list_catalog(self) -> str:
        if not self.manifests:
            return "当前没有发现可用技能。"
        lines = []
        for manifest in self.manifests.values():
            lines.append(f"- {manifest.name}: {manifest.description}")
        return "\n".join(lines)

    def available_names(self) -> List[str]:
        return sorted(self.manifests)

    def load_skill(self, name: str) -> str:
        manifest = self.manifests.get(str(name or "").strip())
        if not manifest:
            available = ", ".join(self.available_names()) or "无"
            return f"Skill not found: {name}\n可用技能: {available}"

        entry_file = manifest.entry_file.resolve()
        try:
            entry_file.relative_to(self.skills_root.resolve())
        except ValueError:
            return f"Skill path escapes skills root: {name}"

        text = entry_file.read_text(encoding="utf-8")
        max_chars = int(self.config.get("MAX_SKILL_CONTENT_CHARS", 12000))
        truncated = len(text) > max_chars
        if truncated:
            text = text[:max_chars]

        relative_path = entry_file.relative_to(WORKDIR)
        result = [
            f"技能名称: {manifest.name}",
            f"入口文件: {relative_path}",
            "",
            text,
        ]
        if truncated:
            result.append("\n[Skill content truncated: 内容过长，已截断。需要更多信息时，请按 SKILL.md 指引读取相关引用文件。]")
        return "\n".join(result)


def _first_heading_or_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        return stripped.lstrip("#").strip()
    return ""


SKILL_REGISTRY = SkillRegistry(skill_config)
SKILL_REGISTRY.scan_skills()
