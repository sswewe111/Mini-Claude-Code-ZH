import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from prompts.memory_prompts import (
    MEMORY_EXTRACT_PROMPT,
    MEMORY_RELEVANCE_HEADER,
    MEMORY_RELEVANCE_PROMPT,
)
from state.memory_state import MemoryItem, MemorySelection, MemoryState
from utils.config_handler import memory_config
from utils.logger_handler import logger
from utils.path_sandbox import WORKDIR, safe_path


VALID_SCOPES = {"private", "team"}
VALID_TYPES = {"user", "feedback", "project", "reference"}
INJECTED_MEMORY_PREFIX = "[Memory context]"


class MemoryManager:
    """文件型长期记忆管理器：索引常驻，正文按需加载。"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.state = MemoryState()

    def enabled(self) -> bool:
        return bool(self.config.get("ENABLE_MEMORY", True))

    def ensure_dirs(self) -> None:
        if not self.enabled():
            return
        for scope in VALID_SCOPES:
            directory = self._scope_dir(scope)
            directory.mkdir(parents=True, exist_ok=True)
            index_path = directory / "MEMORY.md"
            if not index_path.exists():
                index_path.write_text("# Memory\n\n", encoding="utf-8")

    def load_index_prompt(self) -> str:
        """读取 private/team 的 MEMORY.md 索引，用于注入 system prompt。"""
        if not self.enabled():
            return ""
        self.ensure_dirs()
        max_lines = int(self.config.get("MAX_INDEX_LINES", 200))
        sections = []
        for scope in ("private", "team"):
            index_path = self._scope_dir(scope) / "MEMORY.md"
            text = index_path.read_text(encoding="utf-8") if index_path.exists() else "# Memory\n"
            lines = text.splitlines()[:max_lines]
            sections.append(f"## {scope} memory index\n" + "\n".join(lines))
        prompt = "\n\n".join(sections)
        self.state.loaded_index_text = prompt
        return prompt

    def scan_memory(self, scope: Optional[str] = None) -> List[MemoryItem]:
        """扫描记忆文件，只读取 frontmatter 元数据。"""
        if not self.enabled():
            return []
        self.ensure_dirs()
        scopes = [scope] if scope else ["private", "team"]
        items: List[MemoryItem] = []
        for active_scope in scopes:
            self._validate_scope(active_scope)
            for path in self._scope_dir(active_scope).glob("*.md"):
                if path.name == "MEMORY.md":
                    continue
                item = self._read_memory_item(path, active_scope)
                if item:
                    items.append(item)
        max_files = int(self.config.get("MAX_MEMORY_FILES", 200))
        items.sort(key=lambda item: item.updated_at or item.path.stat().st_mtime, reverse=True)
        return items[:max_files]

    def select_relevant_memories(
        self,
        messages: list,
        client=None,
        model_id: Optional[str] = None,
    ) -> MemorySelection:
        """优先用 LLM side-query 选择相关记忆；失败时回退关键词匹配。"""
        items = self.scan_memory()
        if not items:
            return MemorySelection()

        if client and model_id:
            selection = self._select_relevant_memories_with_llm(messages, items, client, model_id)
            if selection.source != "llm_failed":
                return selection

        return self._select_relevant_memories_by_keyword(messages, items)

    def _select_relevant_memories_with_llm(
        self,
        messages: list,
        items: List[MemoryItem],
        client,
        model_id: str,
    ) -> MemorySelection:
        max_items = int(self.config.get("MAX_RELEVANT_MEMORIES", 5))
        catalog = self._memory_catalog(items)
        recent = self._recent_text(messages)
        prompt = (
            f"最近对话：\n{recent[:8000]}\n\n"
            f"候选长期记忆目录：\n{catalog}\n\n"
            f"请最多选择 {max_items} 个相关 filename。"
        )
        timeout = self._llm_timeout_seconds()
        try:
            logger.info("开始 LLM Memory 召回: candidates=%s, timeout=%ss", len(items), timeout)
            response = client.chat.completions.create(
                model=model_id,
                messages=[
                    {"role": "system", "content": MEMORY_RELEVANCE_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=int(self.config.get("MEMORY_RELEVANCE_MAX_TOKENS", 300)),
                timeout=timeout,
            )
            text = response.choices[0].message.content or "[]"
            filenames = self._parse_json_string_array(text)
        except Exception as exc:
            logger.warning("LLM Memory 召回失败，回退关键词匹配: %s", exc)
            return MemorySelection(source="llm_failed", reason=str(exc))

        by_filename = {item.path.name: item for item in items}
        selected: List[MemoryItem] = []
        for filename in filenames:
            item = by_filename.get(filename)
            if item and item not in selected:
                selected.append(item)
            if len(selected) >= max_items:
                break

        logger.info("LLM Memory 召回完成: selected=%s", [item.path.name for item in selected])
        return MemorySelection(
            items=selected,
            reason="llm side-query",
            source="llm",
        )

    def _select_relevant_memories_by_keyword(
        self,
        messages: list,
        items: List[MemoryItem],
    ) -> MemorySelection:
        query = self._recent_text(messages).lower()
        scored = []
        for item in items:
            haystack = f"{item.name} {item.description} {item.type} {item.scope}".lower()
            score = sum(1 for token in self._tokens(query) if token and token in haystack)
            if score:
                scored.append((score, item))

        # 如果关键词没有命中，保守地不注入正文；索引仍在 system prompt 中。
        scored.sort(key=lambda pair: pair[0], reverse=True)
        max_items = int(self.config.get("MAX_RELEVANT_MEMORIES", 5))
        selected = [item for _, item in scored[:max_items]]
        return MemorySelection(items=selected, reason="keyword match", source="keyword")

    def inject_relevant_memories(
        self,
        messages: list,
        client=None,
        model_id: Optional[str] = None,
    ) -> None:
        """BeforeModelCall 使用：移除旧注入，再注入本轮相关记忆正文。"""
        if not self.enabled():
            return
        self._remove_injected_memory(messages)
        selection = self.select_relevant_memories(messages, client=client, model_id=model_id)
        prompt = self.load_relevant_memory_prompt(selection)
        if not prompt:
            return
        messages.append({"role": "user", "content": prompt})
        self.state.loaded_memory_paths = [str(item.path.relative_to(WORKDIR)) for item in selection.items]
        logger.info("注入 Memory context: items=%s", len(selection.items))

    def load_relevant_memory_prompt(self, selection: MemorySelection) -> str:
        if not selection.items:
            return ""
        max_file_chars = int(self.config.get("MAX_MEMORY_FILE_CHARS", 4096))
        max_total_chars = int(self.config.get("MAX_TOTAL_MEMORY_CHARS", 60000))
        chunks = [f"{INJECTED_MEMORY_PREFIX}\n{MEMORY_RELEVANCE_HEADER}"]
        total = len(chunks[0])
        for item in selection.items:
            text = item.path.read_text(encoding="utf-8")[:max_file_chars]
            chunk = f"\n\n## {item.scope}/{item.type}: {item.name}\n{text}"
            if total + len(chunk) > max_total_chars:
                break
            chunks.append(chunk)
            total += len(chunk)
        return "".join(chunks)

    def save_memory(
        self,
        name: str,
        scope: str,
        type: str,
        description: str,
        content: str,
    ) -> str:
        self.ensure_dirs()
        self._validate_scope(scope)
        self._validate_type(type)
        if type == "user" and scope != "private":
            raise ValueError("user memory must use private scope")
        if not name.strip() or not description.strip() or not content.strip():
            raise ValueError("name, description and content are required")

        slug = self._slugify(name)
        path = self._scope_dir(scope) / f"{slug}.md"
        timestamp = self._now()
        body = (
            "---\n"
            f"name: {name.strip()}\n"
            f"description: {description.strip()}\n"
            f"type: {type.strip()}\n"
            f"scope: {scope.strip()}\n"
            f"updated_at: {timestamp}\n"
            "---\n\n"
            f"{content.strip()}\n"
        )
        path.write_text(body, encoding="utf-8")
        self.rebuild_index(scope)
        self.state.saved_this_turn = True
        logger.info("保存 Memory: %s/%s %s", scope, type, path.name)
        return f"已保存 {scope}/{type} memory: {name.strip()}"

    def forget_memory(self, name_or_path: str, scope: str, reason: str = "") -> str:
        self.ensure_dirs()
        self._validate_scope(scope)
        target = self._resolve_memory_path(name_or_path, scope)
        if not target.exists():
            raise FileNotFoundError(f"memory not found: {name_or_path}")
        target.unlink()
        self.rebuild_index(scope)
        self.state.saved_this_turn = True
        if reason:
            logger.info("删除 Memory: %s, reason=%s", target.name, reason)
        else:
            logger.info("删除 Memory: %s", target.name)
        return f"已删除 {scope} memory: {target.name}"

    def rebuild_index(self, scope: str) -> None:
        self._validate_scope(scope)
        directory = self._scope_dir(scope)
        items = self.scan_memory(scope)
        lines = ["# Memory", ""]
        for item in items:
            lines.append(f"- [{item.name}]({item.path.name}) - {item.description}")
        (directory / "MEMORY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def extract_memories(self, messages: list, client=None, model_id: Optional[str] = None) -> None:
        """Stop Hook 使用：从最近对话中自动提取长期记忆。"""
        if not self.enabled() or not self.config.get("AUTO_EXTRACT_MEMORY", True):
            return
        if self.state.saved_this_turn:
            logger.info("本轮已主动写入 Memory，跳过自动提取")
            self.state.saved_this_turn = False
            return
        if not client or not model_id:
            return

        recent_count = int(self.config.get("EXTRACT_RECENT_MESSAGES", 12))
        recent = messages[-recent_count:]
        existing = "\n".join(
            f"- {item.scope}/{item.type}/{item.name}: {item.description}"
            for item in self.scan_memory()
        )
        prompt = (
            f"当前日期：{datetime.now().date().isoformat()}\n\n"
            f"已有记忆索引：\n{existing or '(empty)'}\n\n"
            f"最近对话 JSON：\n{json.dumps(recent, ensure_ascii=False)[:12000]}"
        )
        timeout = self._llm_timeout_seconds()
        try:
            logger.info("开始自动提取 Memory: timeout=%ss", timeout)
            response = client.chat.completions.create(
                model=model_id,
                messages=[
                    {"role": "system", "content": MEMORY_EXTRACT_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=int(self.config.get("MEMORY_EXTRACT_MAX_TOKENS", 1200)),
                timeout=timeout,
            )
            text = response.choices[0].message.content or "[]"
            records = self._parse_json_array(text)
        except Exception as exc:
            logger.warning("自动提取 Memory 失败: %s", exc)
            return

        saved = 0
        for record in records:
            try:
                self.save_memory(
                    name=str(record.get("name", "")),
                    scope=str(record.get("scope", "private")),
                    type=str(record.get("type", "feedback")),
                    description=str(record.get("description", "")),
                    content=str(record.get("content", "")),
                )
                saved += 1
            except Exception as exc:
                logger.warning("跳过无效 Memory 提取结果: %s", exc)
        if saved:
            logger.info("自动提取 Memory 完成: saved=%s", saved)
        self.state.saved_this_turn = False
        self.dream(client, model_id)

    def dream(self, client=None, model_id: Optional[str] = None) -> None:
        """第一版 Dream 只做门控和索引重建，LLM 合并留给后续增强。"""
        if not self.enabled() or not self.config.get("DREAM_ENABLED", True):
            return
        items = self.scan_memory()
        if len(items) < int(self.config.get("DREAM_MIN_FILES", 10)):
            return
        lock = safe_path(".memory/.dream-lock")
        if lock.exists() and not self._lock_expired(lock):
            return
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text(self._now(), encoding="utf-8")
        for scope in VALID_SCOPES:
            self.rebuild_index(scope)
        self.state.last_dream_at = self._now()
        logger.info("Memory Dream 完成: files=%s", len(items))

    def _scope_dir(self, scope: str) -> Path:
        key = "PRIVATE_MEMORY_DIR" if scope == "private" else "TEAM_MEMORY_DIR"
        return safe_path(self.config.get(key, f".memory/{scope}"))

    def _read_memory_item(self, path: Path, default_scope: str) -> Optional[MemoryItem]:
        text = path.read_text(encoding="utf-8")
        meta = self._parse_frontmatter(text)
        if not meta:
            return None
        return MemoryItem(
            name=meta.get("name", path.stem),
            description=meta.get("description", ""),
            type=meta.get("type", "feedback"),
            scope=meta.get("scope", default_scope),
            path=path,
            updated_at=meta.get("updated_at", ""),
        )

    def _parse_frontmatter(self, text: str) -> Dict[str, str]:
        if not text.startswith("---"):
            return {}
        end = text.find("\n---", 3)
        if end == -1:
            return {}
        meta: Dict[str, str] = {}
        for line in text[3:end].splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip().strip("\"'")
        return meta

    def _resolve_memory_path(self, name_or_path: str, scope: str) -> Path:
        raw = name_or_path.strip()
        directory = self._scope_dir(scope)
        candidates = [directory / raw]
        if not raw.endswith(".md"):
            candidates.append(directory / f"{self._slugify(raw)}.md")
        for candidate in candidates:
            resolved = candidate.resolve()
            try:
                resolved.relative_to(directory.resolve())
            except ValueError:
                continue
            if resolved.exists():
                return resolved
        return candidates[-1]

    def _remove_injected_memory(self, messages: list) -> None:
        messages[:] = [
            message for message in messages
            if not (
                message.get("role") == "user"
                and isinstance(message.get("content"), str)
                and message["content"].startswith(INJECTED_MEMORY_PREFIX)
            )
        ]

    def _recent_text(self, messages: list) -> str:
        recent_count = min(len(messages), 8)
        return json.dumps(messages[-recent_count:], ensure_ascii=False)

    def _memory_catalog(self, items: List[MemoryItem]) -> str:
        lines = []
        for item in items:
            lines.append(
                json.dumps(
                    {
                        "filename": item.path.name,
                        "scope": item.scope,
                        "type": item.type,
                        "name": item.name,
                        "description": item.description,
                    },
                    ensure_ascii=False,
                )
            )
        return "\n".join(lines)

    def _tokens(self, text: str) -> List[str]:
        words = re.findall(r"[a-zA-Z0-9_\-\u4e00-\u9fff]+", text)
        tokens: List[str] = []
        for word in words:
            tokens.append(word.lower())
            if len(word) > 6:
                tokens.extend(word[i:i + 4].lower() for i in range(0, len(word) - 3, 2))
        return tokens[:200]

    def _slugify(self, text: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9_\-\u4e00-\u9fff]+", "-", text.strip()).strip("-").lower()
        return slug or "memory"

    def _parse_json_array(self, text: str) -> List[dict]:
        match = re.search(r"\[.*\]", text, flags=re.S)
        if not match:
            return []
        data = json.loads(match.group(0))
        return data if isinstance(data, list) else []

    def _parse_json_string_array(self, text: str) -> List[str]:
        match = re.search(r"\[.*\]", text, flags=re.S)
        if not match:
            return []
        data = json.loads(match.group(0))
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, str)]

    def _lock_expired(self, lock: Path) -> bool:
        ttl = int(self.config.get("MEMORY_LOCK_TTL_MINUTES", 60)) * 60
        return (datetime.now().timestamp() - lock.stat().st_mtime) > ttl

    def _llm_timeout_seconds(self) -> float:
        timeout = float(self.config.get("MEMORY_LLM_TIMEOUT_SECONDS", 8))
        return timeout if timeout > 0 else 8.0

    def _validate_scope(self, scope: str) -> None:
        if scope not in VALID_SCOPES:
            raise ValueError(f"invalid memory scope: {scope}")

    def _validate_type(self, type: str) -> None:
        if type not in VALID_TYPES:
            raise ValueError(f"invalid memory type: {type}")

    def _now(self) -> str:
        return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


MEMORY_MANAGER = MemoryManager(memory_config)
