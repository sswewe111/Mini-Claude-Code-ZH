TEAM_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "spawn_teammate",
            "description": "创建一个 teammate，并在独立线程中处理分配给它的任务。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "teammate 名称，例如 alice。"},
                    "role": {"type": "string", "description": "teammate 角色，例如 backend tester。"},
                    "prompt": {"type": "string", "description": "交给 teammate 的自包含任务说明。"},
                },
                "required": ["name", "role", "prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "team_send_message",
            "description": "向 Lead 或某个 teammate 发送团队消息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "收件人名称，例如 lead 或 alice。"},
                    "content": {"type": "string", "description": "消息正文。"},
                    "msg_type": {
                        "type": "string",
                        "description": "消息类型，默认 message；完成交付时可用 result。",
                    },
                },
                "required": ["to", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "team_broadcast",
            "description": "向多个 teammate 广播同一条消息；不传 recipients 时发给所有活跃 teammate。",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "广播正文。"},
                    "recipients": {
                        "type": "array",
                        "description": "可选，收件人列表。",
                        "items": {"type": "string"},
                    },
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "team_check_inbox",
            "description": "读取 Lead 或 teammate 的团队收件箱。",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent": {
                        "type": "string",
                        "description": "可选，收件箱名称；默认读取 lead。",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "team_list",
            "description": "列出当前团队成员、状态、轮次和最后活跃时间。",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "team_request_shutdown",
            "description": "向指定 teammate 发送优雅关闭请求，返回 request_id。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "teammate 名称，例如 alice。"},
                    "reason": {"type": "string", "description": "可选，关闭原因。"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "team_review_plan",
            "description": "审批 teammate 提交的计划审批请求。",
            "parameters": {
                "type": "object",
                "properties": {
                    "request_id": {"type": "string", "description": "计划审批请求 ID。"},
                    "approve": {"type": "boolean", "description": "true 表示批准，false 表示拒绝。"},
                    "feedback": {"type": "string", "description": "审批反馈或拒绝原因。"},
                },
                "required": ["request_id", "approve"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "team_protocol_status",
            "description": "查看团队协议请求状态，包含 pending/approved/rejected。",
            "parameters": {
                "type": "object",
                "properties": {
                    "request_id": {"type": "string", "description": "可选，只查看某个请求。"},
                    "include_resolved": {"type": "boolean", "description": "是否包含已完成请求，默认 true。"},
                },
            },
        },
    },
]


TEAMMATE_PROTOCOL_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "team_submit_plan",
            "description": "向 Lead 提交计划审批请求，等待批准后再执行高风险修改。",
            "parameters": {
                "type": "object",
                "properties": {
                    "plan": {"type": "string", "description": "计划正文，说明步骤、风险和预期改动。"},
                    "risk_level": {"type": "string", "description": "可选，风险等级，例如 low/medium/high。"},
                    "target_files": {
                        "type": "array",
                        "description": "可选，计划涉及的文件列表。",
                        "items": {"type": "string"},
                    },
                },
                "required": ["plan"],
            },
        },
    },
    TEAM_TOOLS[7],
]


TEAMMATE_TASK_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "task_list",
            "description": "查看持久任务看板摘要。teammate 用它了解当前任务和依赖状态。",
            "parameters": {
                "type": "object",
                "properties": {
                    "include_completed": {"type": "boolean", "description": "是否包含 completed/cancelled 任务。"},
                    "owner": {"type": "string", "description": "可选，只查看某个 owner 的任务。"},
                    "status": {
                        "type": "string",
                        "enum": ["pending", "in_progress", "completed", "cancelled"],
                        "description": "可选，只查看指定状态。",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_get",
            "description": "读取一个持久任务的完整 JSON。",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "任务 ID，例如 task_000001。"}
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_complete",
            "description": "完成当前 teammate 认领的任务。owner 必须使用 teammate 自己的名称。",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "任务 ID。"},
                    "owner": {"type": "string", "description": "完成者名称，必须是当前 teammate。"},
                    "summary": {"type": "string", "description": "完成摘要。"},
                },
                "required": ["task_id"],
            },
        },
    },
]


TEAMMATE_AVAILABLE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "在当前工作目录执行一条命令；Windows 使用 PowerShell，Linux/macOS 使用 bash。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的命令"}
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取工作区内的文件内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径，支持相对路径"},
                    "limit": {"type": "integer", "description": "最多读取的行数"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "向工作区内文件写入内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径，支持相对路径"},
                    "content": {"type": "string", "description": "要写入的完整内容"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "在工作区内文件中精确替换一段文本。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径，支持相对路径"},
                    "old_text": {"type": "string", "description": "需要被替换的原文，必须精确匹配"},
                    "new_text": {"type": "string", "description": "替换后的文本"},
                },
                "required": ["path", "old_text", "new_text"],
            },
        },
    },
    TEAM_TOOLS[1],
    TEAM_TOOLS[3],
] + TEAMMATE_PROTOCOL_TOOLS + TEAMMATE_TASK_TOOLS
