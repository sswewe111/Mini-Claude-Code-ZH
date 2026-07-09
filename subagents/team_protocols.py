from typing import List, Tuple

from state.team_state import TeamMessage


def handle_teammate_protocol_messages(
    member_name: str,
    messages: List[TeamMessage],
    team_manager,
) -> Tuple[str, List[TeamMessage]]:
    """处理 teammate inbox 中的协议消息。

    返回值 action:
    - "continue": 继续正常模型循环
    - "shutdown": 线程应退出
    """
    remaining: List[TeamMessage] = []
    for message in messages:
        if message.type == "shutdown_request":
            request_id = str(message.metadata.get("request_id") or "")
            reason = str(message.metadata.get("reason") or message.content or "")
            summary = f"teammate {member_name} 已收到关闭请求并完成收尾。原因：{reason or '未提供'}"
            team_manager.send_structured_message(
                sender=member_name,
                to=team_manager.lead_name,
                content=summary,
                msg_type="shutdown_approved",
                metadata={
                    "request_id": request_id,
                    "protocol": "shutdown",
                    "approve": True,
                    "summary": summary,
                },
            )
            team_manager.send_structured_message(
                sender=member_name,
                to=team_manager.lead_name,
                content=f"teammate {member_name} 已退出。",
                msg_type="teammate_terminated",
                metadata={"request_id": request_id, "protocol": "shutdown"},
            )
            team_manager.record_member_status(member_name, "stopped")
            return "shutdown", remaining

        if message.type in ("plan_approval_approved", "plan_approval_rejected"):
            status = "已批准" if message.type == "plan_approval_approved" else "已拒绝"
            feedback = str(message.metadata.get("feedback") or message.content or "")
            remaining.append(
                TeamMessage(
                    id=message.id,
                    sender=message.sender,
                    recipient=message.recipient,
                    type=message.type,
                    content=(
                        f"计划审批{status}。request_id={message.metadata.get('request_id', '')}\n"
                        f"反馈：{feedback}"
                    ),
                    created_at=message.created_at,
                    correlation_id=message.correlation_id,
                    metadata=message.metadata,
                )
            )
            continue

        remaining.append(message)
    return "continue", remaining
