from dataclasses import dataclass


@dataclass
class RecoveryState:
    """一次 Agent 运行中的错误恢复状态。"""

    transient_retries: int = 0
    context_retries: int = 0
    continuation_retries: int = 0
    consecutive_overloads: int = 0
    switched_fallback_model: bool = False
    current_model_id: str = ""
    last_error_type: str = ""
    last_error_reason: str = ""
