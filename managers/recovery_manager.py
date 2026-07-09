import random
import time
from typing import Callable, Dict, List, Optional

from prompts.recovery_prompts import CONTINUATION_PROMPT
from state.recovery_state import RecoveryState
from utils.config_handler import recovery_config
from utils.logger_handler import logger


class RecoveryManager:
    """模型调用错误恢复管理器。

    这里负责判断“要不要重试”和“怎么重试”，真正的上下文压缩仍交给
    CompactManager，避免 s11 重复实现 s08 的能力。
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or recovery_config
        self.state = RecoveryState()

    def create_chat_completion(
        self,
        client,
        model_id: str,
        build_messages: Callable[[], List[dict]],
        tools: List[dict],
        tool_choice: str = "auto",
        max_tokens: int = 2048,
        compact_manager=None,
        state_messages: Optional[list] = None,
    ):
        """带恢复能力的 Chat Completions 调用。

        build_messages 每次重试都会重新执行。这样 reactive compact 修改
        state.messages 后，下一次请求会拿到压缩后的最新上下文。
        """
        if not self.config.get("ENABLE_RECOVERY", True):
            return client.chat.completions.create(
                model=model_id,
                messages=build_messages(),
                tools=tools,
                tool_choice=tool_choice,
                max_tokens=max_tokens,
            )

        self.state.current_model_id = self.state.current_model_id or model_id

        while True:
            try:
                response = client.chat.completions.create(
                    model=self.state.current_model_id,
                    messages=build_messages(),
                    tools=tools,
                    tool_choice=tool_choice,
                    max_tokens=max_tokens,
                )
                self.state.transient_retries = 0
                self.state.consecutive_overloads = 0
                return response
            except Exception as exc:
                error_type = self.classify_error(exc)
                self.state.last_error_type = error_type
                self.state.last_error_reason = str(exc)

                if error_type == "context_length":
                    if self._recover_context(compact_manager, state_messages, client):
                        continue
                    raise

                if self._should_retry_transient(error_type, exc):
                    self._retry_transient(error_type, exc)
                    continue

                logger.exception("[recovery] 不可恢复的模型调用错误: type=%s", error_type)
                raise

    def build_continuation_message(self, finish_reason: str) -> Optional[dict]:
        """输出被截断时生成续写消息；超过次数后不再继续。"""
        if finish_reason != "length":
            return None
        if not self.config.get("ENABLE_RECOVERY", True):
            return None

        max_retries = int(self.config.get("MAX_CONTINUATION_RETRIES", 2))
        if self.state.continuation_retries >= max_retries:
            logger.warning("[recovery] 输出截断续写次数已耗尽: %s", max_retries)
            return None

        self.state.continuation_retries += 1
        logger.warning(
            "[recovery] 模型输出被截断，注入续写提示: retry=%s/%s",
            self.state.continuation_retries,
            max_retries,
        )
        return {"role": "user", "content": CONTINUATION_PROMPT}

    def classify_error(self, exc: Exception) -> str:
        """把不同 OpenAI 兼容服务的异常归一成少量恢复类型。"""
        if self.is_context_length_error(exc):
            return "context_length"

        status_code = self._status_code(exc)
        retry_codes = {int(code) for code in self.config.get("RETRY_STATUS_CODES", [])}
        if status_code in retry_codes:
            if status_code in {500, 502, 503, 504, 529}:
                return "server_overloaded"
            if status_code == 429:
                return "rate_limit"
            return "transient"

        text = str(exc).lower()
        transient_keywords = self.config.get("TRANSIENT_ERROR_KEYWORDS", [])
        if any(str(keyword).lower() in text for keyword in transient_keywords):
            if "overload" in text or "temporarily unavailable" in text:
                return "server_overloaded"
            if "rate limit" in text or "too many requests" in text:
                return "rate_limit"
            return "network_timeout"

        return "unknown"

    def is_context_length_error(self, exc: Exception) -> bool:
        text = str(exc).lower()
        keywords = self.config.get("CONTEXT_ERROR_KEYWORDS", [])
        return any(str(keyword).lower() in text for keyword in keywords)

    def _recover_context(self, compact_manager, state_messages, client) -> bool:
        max_retries = int(self.config.get("MAX_CONTEXT_RECOVERY_RETRIES", 1))
        if self.state.context_retries >= max_retries:
            logger.error("[recovery] 上下文超限恢复次数已耗尽: %s", max_retries)
            return False
        if not compact_manager or state_messages is None:
            logger.error("[recovery] 缺少 compact_manager 或 state_messages，无法恢复上下文超限")
            return False

        self.state.context_retries += 1
        logger.warning(
            "[recovery] 模型上下文过长，执行 reactive compact: retry=%s/%s",
            self.state.context_retries,
            max_retries,
        )
        return bool(compact_manager.reactive_compact(
            state_messages,
            client,
            self.state.current_model_id,
        ))

    def _should_retry_transient(self, error_type: str, exc: Exception) -> bool:
        if error_type not in {"rate_limit", "server_overloaded", "network_timeout", "transient"}:
            return False
        max_retries = int(self.config.get("MAX_TRANSIENT_RETRIES", 3))
        if self.state.transient_retries >= max_retries:
            logger.error(
                "[recovery] 临时错误重试次数已耗尽: type=%s, retries=%s",
                error_type,
                max_retries,
            )
            return False
        return True

    def _retry_transient(self, error_type: str, exc: Exception) -> None:
        self.state.transient_retries += 1
        if error_type == "server_overloaded":
            self.state.consecutive_overloads += 1
            self._maybe_switch_fallback_model()

        delay = self.backoff_delay(self.state.transient_retries, self._retry_after(exc))
        logger.warning(
            "[recovery] 模型临时错误，等待后重试: type=%s, retry=%s, delay=%.2fs",
            error_type,
            self.state.transient_retries,
            delay,
        )
        time.sleep(delay)

    def _maybe_switch_fallback_model(self) -> None:
        fallback_model = str(self.config.get("FALLBACK_MODEL_ID") or "").strip()
        threshold = int(self.config.get("FALLBACK_AFTER_OVERLOADS", 3))
        if not fallback_model or self.state.switched_fallback_model:
            return
        if self.state.consecutive_overloads < threshold:
            return

        logger.warning(
            "[recovery] 连续过载，切换备用模型: %s -> %s",
            self.state.current_model_id,
            fallback_model,
        )
        self.state.current_model_id = fallback_model
        self.state.switched_fallback_model = True

    def backoff_delay(self, attempt: int, retry_after: Optional[float] = None) -> float:
        if retry_after is not None and retry_after >= 0:
            return retry_after

        base = float(self.config.get("BACKOFF_BASE_SECONDS", 1))
        max_delay = float(self.config.get("BACKOFF_MAX_SECONDS", 20))
        jitter_ratio = float(self.config.get("BACKOFF_JITTER_RATIO", 0.25))
        delay = min(base * (2 ** max(attempt - 1, 0)), max_delay)
        return delay + random.uniform(0, delay * jitter_ratio)

    def _status_code(self, exc: Exception) -> Optional[int]:
        for attr in ("status_code", "code"):
            value = getattr(exc, attr, None)
            if isinstance(value, int):
                return value

        response = getattr(exc, "response", None)
        value = getattr(response, "status_code", None)
        return value if isinstance(value, int) else None

    def _retry_after(self, exc: Exception) -> Optional[float]:
        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", None)
        if not headers:
            return None
        value = headers.get("retry-after") or headers.get("Retry-After")
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None
