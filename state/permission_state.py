from dataclasses import dataclass
@dataclass
class PermissionResult:
    allowed: bool
    reason: str = ""
    needs_approval: bool = False