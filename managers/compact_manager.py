import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from prompts.compact_prompts import COMPACT_HISTORY_PROMPT
from state.compact_state import CompactState, PersistedToolOutput
from utils.config_handler import compact_config
from utils.logger_handler import logger
from utils.normalize_messages import normalize_messages
from utils.path_sandbox import WORKDIR, safe_path
from utils.token_counter import estimate_message_tokens


PERSISTED_MARKER = "<persisted-tool-output"


class CompactManager:
    """Context Compact 管理器：负责压缩 messages，但不直接属于 Agent Loop。"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.state = CompactState()

    def request_manual_compact(self, focus: str = "") -> str:
        """由 compact 工具设置一次手动压缩请求，下一轮 BeforeModelCall 执行。"""
        self.state.pending_manual_focus = focus or "模型主动请求压缩上下文"
        logger.info("收到手动 compact 请求: %s", self.state.pending_manual_focus)
        return "已收到 compact 请求，将在下一轮模型调用前压缩上下文。"

    def pre_model_compact(
        self,
        messages: list,
        client=None,
        model_id: Optional[str] = None,
        focus: str = "",
        allow_llm: bool = True,
    ) -> None:
        """模型调用前的压缩入口；直接原地修改 messages 列表。"""
        if not self.config.get("ENABLE_AUTO_COMPACT", True):
            return

        self.persist_large_tool_outputs(messages)
        self.micro_compact_tool_results(messages)
        self.snip_middle_messages(messages)

        token_count = estimate_message_tokens(messages)
        pending_focus = self.state.pending_manual_focus
        should_summary = token_count >= int(self.config.get("AUTO_COMPACT_TOKEN_THRESHOLD", 24000))
        if pending_focus:
            should_summary = True
            focus = pending_focus
            self.state.pending_manual_focus = ""

        if should_summary and allow_llm and client and model_id:
            logger.info("触发 LLM compact: tokens≈%s, focus=%s", token_count, focus)
            self.compact_history(messages, client, model_id, focus=focus)

    def persist_tool_output(
        self,
        output: str,
        tool_name: str = "tool",
        tool_call_id: str = "",
    ) -> str:
        """PostToolUse 阶段压缩单次工具输出，避免大结果进入 messages。"""
        if not isinstance(output, str):
            output = str(output)
        limit = int(self.config.get("LARGE_TOOL_OUTPUT_CHARS", 12000))
        if len(output) <= limit or output.startswith(PERSISTED_MARKER):
            return output

        return self._persist_output(
            output=output,
            tool_name=tool_name,
            tool_call_id=tool_call_id or tool_name,
        )

    def persist_large_tool_outputs(self, messages: list) -> None:
        """扫描已存在的 tool 消息，把超大内容落盘并替换为占位。"""
        for message in messages:
            if message.get("role") != "tool":
                continue
            content = message.get("content", "")
            if not isinstance(content, str) or content.startswith(PERSISTED_MARKER):
                continue
            compacted = self.persist_tool_output(
                content,
                tool_name="tool",
                tool_call_id=message.get("tool_call_id", "tool"),
            )
            if compacted != content:
                message["content"] = compacted

    def micro_compact_tool_results(self, messages: list) -> None:
        """保留最近 N 条完整工具结果，更旧的长结果替换为占位。"""
        keep_recent = int(self.config.get("KEEP_RECENT_TOOL_RESULTS", 4))
        tool_indices = [i for i, msg in enumerate(messages) if msg.get("role") == "tool"]
        if len(tool_indices) <= keep_recent:
            return

        for index in tool_indices[:-keep_recent]:
            content = messages[index].get("content", "")
            if not isinstance(content, str) or content.startswith("[Earlier tool result compacted"):
                continue
            if len(content) <= 300:
                continue
            messages[index]["content"] = (
                "[Earlier tool result compacted. "
                "如需完整内容，请根据上下文重新读取对应文件或重新执行工具。]"
            )

    def snip_middle_messages(self, messages: list) -> None:
        """消息条数过多时裁剪中间历史，并尽量保护 tool_call/tool_result 顺序。"""
        max_messages = int(self.config.get("MAX_MESSAGES_BEFORE_SNIP", 60))
        if len(messages) <= max_messages:
            return

        keep_head = int(self.config.get("KEEP_HEAD_MESSAGES", 3))
        keep_tail = int(self.config.get("KEEP_TAIL_MESSAGES", 45))
        if keep_head + keep_tail >= len(messages):
            return

        head_end = min(keep_head, len(messages))
        tail_start = max(head_end, len(messages) - keep_tail)

        # 不让 tail 从孤立 tool 消息开始；如果第一条是 tool，向前包含对应 assistant。
        while tail_start > head_end and messages[tail_start].get("role") == "tool":
            tail_start -= 1

        # 不让 head 以带 tool_calls 的 assistant 结束，否则其 tool result 会被裁掉。
        while head_end > 0 and self._has_tool_calls(messages[head_end - 1]):
            head_end -= 1

        snipped = tail_start - head_end
        if snipped <= 0:
            return

        placeholder = {
            "role": "user",
            "content": f"[Context compacted: 中间 {snipped} 条历史消息已裁剪，完整记录见 transcript 或后续摘要。]",
        }
        messages[:] = messages[:head_end] + [placeholder] + messages[tail_start:]
        messages[:] = normalize_messages(messages)
        logger.info("已裁剪中间历史消息: snipped=%s, remaining=%s", snipped, len(messages))

    def compact_history(self, messages: list, client, model_id: str, focus: str = "") -> None:
        """用模型把当前历史总结成一条摘要消息，并写 transcript 留痕。"""
        transcript_path = self.write_transcript(messages)
        summary_input = self._serialize_for_summary(messages)
        user_prompt = (
            f"压缩重点：{focus or '保留继续完成当前任务所需的信息'}\n\n"
            f"Transcript path: {transcript_path}\n\n"
            f"对话历史：\n{summary_input}"
        )
        response = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": COMPACT_HISTORY_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=int(self.config.get("MAX_OUTPUT_TOKENS", 2048)),
        )
        summary = response.choices[0].message.content or ""
        messages[:] = [{
            "role": "user",
            "content": (
                "[Context compacted]\n"
                f"完整 transcript: {transcript_path}\n\n"
                f"{summary}"
            ),
        }]
        self.state.has_compacted = True
        self.state.last_summary = summary
        self.state.last_transcript_path = transcript_path
        logger.info("LLM compact 完成: transcript=%s, summary_length=%s", transcript_path, len(summary))

    def reactive_compact(self, messages: list, client, model_id: str) -> bool:
        """上下文过长报错后的应急压缩。超过次数后返回 False。"""
        max_retries = int(self.config.get("MAX_REACTIVE_COMPACT_RETRIES", 1))
        if self.state.reactive_retries >= max_retries:
            return False
        self.state.reactive_retries += 1
        self.compact_history(messages, client, model_id, focus="模型上下文过长后的应急压缩")
        return True

    def write_transcript(self, messages: list) -> str:
        """把完整消息历史写成 JSONL，便于后续追溯。"""
        transcript_dir = safe_path(self.config.get("TRANSCRIPT_DIR", ".transcripts"))
        transcript_dir.mkdir(parents=True, exist_ok=True)
        filename = datetime.now().strftime("transcript_%Y%m%d_%H%M%S_%f.jsonl")
        path = transcript_dir / filename
        with path.open("w", encoding="utf-8") as file:
            for message in messages:
                file.write(json.dumps(message, ensure_ascii=False) + "\n")
        return str(path.relative_to(WORKDIR))

    def _persist_output(self, output: str, tool_name: str, tool_call_id: str) -> str:
        output_dir = safe_path(self.config.get("TOOL_OUTPUT_DIR", ".task_outputs/tool-results"))
        output_dir.mkdir(parents=True, exist_ok=True)

        safe_tool = re.sub(r"[^a-zA-Z0-9_-]+", "_", tool_name or "tool")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = output_dir / f"{timestamp}_{safe_tool}.txt"
        path.write_text(output, encoding="utf-8")

        preview_chars = int(self.config.get("TOOL_OUTPUT_PREVIEW_CHARS", 1200))
        preview = output[:preview_chars]
        relative_path = str(path.relative_to(WORKDIR))
        record = PersistedToolOutput(
            tool_call_id=tool_call_id,
            path=relative_path,
            original_chars=len(output),
            preview=preview,
        )
        self.state.compacted_tool_outputs[tool_call_id] = record
        logger.info("工具输出已落盘: path=%s, chars=%s", relative_path, len(output))
        return (
            f'<persisted-tool-output path="{relative_path}" original_chars="{len(output)}">\n'
            f"{preview}\n"
            "</persisted-tool-output>\n"
            "[完整工具输出已落盘；如需完整内容，请使用 read_file 读取上述 path。]"
        )

    def _serialize_for_summary(self, messages: list) -> str:
        text = json.dumps(messages, ensure_ascii=False, indent=2)
        max_chars = int(self.config.get("MAX_SUMMARY_INPUT_CHARS", 30000))
        if len(text) <= max_chars:
            return text
        return text[-max_chars:]

    def _has_tool_calls(self, message: dict) -> bool:
        return bool(message.get("tool_calls"))


COMPACT_MANAGER = CompactManager(compact_config)
