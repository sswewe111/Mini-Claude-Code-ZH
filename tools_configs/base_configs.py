BASE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "在当前工作目录执行一条命令；Windows 使用 PowerShell，Linux/macOS 使用 bash，并返回 stdout、stderr 和退出码。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的命令"},
                    "run_in_background": {
                        "type": "boolean",
                        "description": "是否把长耗时命令放到后台执行。仅用于安装、构建、完整测试等慢操作。",
                    },
                    "background_owner": {
                        "type": "string",
                        "description": "可选，后台任务 owner，默认 main。",
                    },
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
            "description": "向工作区内文件写入内容；不存在的父目录会自动创建。",
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
    {
        "type": "function",
        "function": {
            "name": "todo",
            "description": "重写当前会话的短期任务计划，用于多步骤任务规划和进度跟踪。",
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "description": "完整的当前计划列表。每次调用都要传入重写后的完整列表。",
                        "items": {
                            "type": "object",
                            "properties": {
                                "content": {
                                    "type": "string",
                                    "description": "计划项内容。",
                                },
                                "status": {
                                    "type": "string",
                                    "enum": ["pending", "in_progress", "completed"],
                                    "description": "计划项状态。",
                                },
                                "activeForm": {
                                    "type": "string",
                                    "description": "可选，描述 in_progress 项正在进行的动作。",
                                },
                            },
                            "required": ["content", "status"],
                        },
                    }
                },
                "required": ["items"],
            },
        },
    },
]


SUBAGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "task",
            "description": (
                "启动一个子 Agent 处理复杂、开放或多步骤的子任务。"
                "默认非 fork 模式；配置开启 fork 后可继承父上下文快照。"
                "返回子 Agent 的最终结论，不返回中间对话。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "交给子 Agent 的自包含任务描述。",
                    },
                    "expected_output": {
                        "type": "string",
                        "description": "可选，父 Agent 期望的返回格式或重点。",
                    },
                },
                "required": ["description"],
            },
        },
    }
]


SKILL_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "load_skill",
            "description": (
                "按技能名加载 skills 目录中对应 SKILL.md 的完整说明。"
                "当任务涉及文档、表格、PDF、PPT、前端设计或联网访问等专门能力时，"
                "先调用此工具读取技能说明，再继续执行。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "技能名，例如 docx、pdf、pptx、xlsx、frontend-design、web-access。",
                    }
                },
                "required": ["name"],
            },
        },
    }
]


COMPACT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "compact",
            "description": (
                "请求压缩当前对话上下文。适合在阶段性任务完成、上下文过长、"
                "或后续只需要保留关键摘要时调用。压缩会在下一轮模型调用前执行。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "focus": {
                        "type": "string",
                        "description": "可选，说明压缩时应该重点保留的信息。",
                    }
                },
            },
        },
    }
]


MEMORY_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": (
                "保存一条跨会话长期记忆。只保存未来仍有价值的用户偏好、"
                "协作反馈、项目背景或外部资源入口；不要保存临时任务状态、敏感信息或可由代码直接读取的信息。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "记忆名称，建议短横线命名，例如 user-prefers-concise-review。",
                    },
                    "scope": {
                        "type": "string",
                        "enum": ["private", "team"],
                        "description": "private 表示当前用户私有记忆；team 表示项目共享记忆。",
                    },
                    "type": {
                        "type": "string",
                        "enum": ["user", "feedback", "project", "reference"],
                        "description": "记忆类型。user 必须使用 private；project/reference 通常使用 team。",
                    },
                    "description": {
                        "type": "string",
                        "description": "一行描述，用于未来判断这条记忆是否相关。",
                    },
                    "content": {
                        "type": "string",
                        "description": "Markdown 正文。feedback/project 建议包含 Why 和 How to apply。",
                    },
                },
                "required": ["name", "scope", "type", "description", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "forget_memory",
            "description": "删除一条错误、过时或用户要求忘记的长期记忆，只能删除 .memory 目录内的记忆。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name_or_path": {
                        "type": "string",
                        "description": "记忆名称或文件名，例如 user-prefers-tabs 或 user-prefers-tabs.md。",
                    },
                    "scope": {
                        "type": "string",
                        "enum": ["private", "team"],
                        "description": "要删除的记忆作用域。",
                    },
                    "reason": {
                        "type": "string",
                        "description": "可选，说明为什么删除这条记忆。",
                    },
                },
                "required": ["name_or_path", "scope"],
            },
        },
    },
]


TASK_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "task_create",
            "description": "创建一个跨会话持久任务。适合把大目标拆成可恢复、可认领的小任务。",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "任务短标题。"},
                    "description": {"type": "string", "description": "完整任务说明，供后续恢复上下文。"},
                    "blocked_by": {
                        "type": "array",
                        "description": "上游依赖任务 ID 列表；这些任务完成前不能认领当前任务。",
                        "items": {"type": "string"},
                    },
                    "metadata": {
                        "type": "object",
                        "description": "可选扩展信息，供后续后台任务、团队或 worktree 使用。",
                    },
                },
                "required": ["subject"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_list",
            "description": "列出持久任务看板摘要，按 in_progress、ready、blocked、completed 排序。",
            "parameters": {
                "type": "object",
                "properties": {
                    "include_completed": {
                        "type": "boolean",
                        "description": "是否包含 completed/cancelled 任务，默认 true。",
                    },
                    "owner": {
                        "type": "string",
                        "description": "可选，只查看某个 owner 的任务。",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["pending", "in_progress", "completed", "cancelled"],
                        "description": "可选，只查看指定状态的任务。",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_get",
            "description": "读取一个持久任务的完整 JSON，包括 description、依赖、owner 和 metadata。",
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
            "name": "task_update",
            "description": "更新持久任务的标题、说明、依赖、owner、状态或 metadata。依赖更新会做环检测。",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "任务 ID。"},
                    "subject": {"type": "string", "description": "可选，新任务标题。"},
                    "description": {"type": "string", "description": "可选，新任务完整说明。"},
                    "active_form": {"type": "string", "description": "可选，进行时短语。"},
                    "blocked_by": {
                        "type": "array",
                        "description": "可选，完整替换后的上游依赖 ID 列表。",
                        "items": {"type": "string"},
                    },
                    "metadata": {"type": "object", "description": "可选，要合并进 metadata 的对象。"},
                    "owner": {"type": "string", "description": "可选，设置或清空 owner。"},
                    "status": {
                        "type": "string",
                        "enum": ["pending", "in_progress", "completed", "cancelled"],
                        "description": "可选，直接更新状态；常规流程优先用 task_claim/task_complete。",
                    },
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_claim",
            "description": "认领一个 ready 的 pending 持久任务，设置 owner 并推进到 in_progress。",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "任务 ID。"},
                    "owner": {"type": "string", "description": "认领者名称，默认 main。"},
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_complete",
            "description": "完成一个 in_progress 持久任务，并返回刚刚解锁的下游任务。",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "任务 ID。"},
                    "owner": {"type": "string", "description": "完成者名称；配置要求 owner 时用于校验。"},
                    "summary": {"type": "string", "description": "可选，完成摘要，会写入 metadata。"},
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_cancel",
            "description": "取消一个未完成的持久任务。取消不会删除任务文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "任务 ID。"},
                    "reason": {"type": "string", "description": "取消原因。"},
                },
                "required": ["task_id"],
            },
        },
    },
]


BACKGROUND_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "background_list",
            "description": "列出后台命令任务状态，包括 running、completed、failed。",
            "parameters": {
                "type": "object",
                "properties": {
                    "include_completed": {
                        "type": "boolean",
                        "description": "是否包含 completed/failed/cancelled 任务，默认 true。",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "background_get",
            "description": "查看指定后台任务的状态、输出路径和输出尾部内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "bg_id": {"type": "string", "description": "后台任务 ID，例如 bg_000001。"},
                    "tail_chars": {
                        "type": "integer",
                        "description": "最多返回输出尾部字符数，默认 2000。",
                    },
                },
                "required": ["bg_id"],
            },
        },
    },
]


CRON_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "schedule_cron",
            "description": "创建一个定时任务。到点后调度器会把 prompt 入队，并在 Agent 空闲时自动交付执行。",
            "parameters": {
                "type": "object",
                "properties": {
                    "cron": {
                        "type": "string",
                        "description": "五段式 cron 表达式：分钟 小时 日 月 星期，例如 */5 * * * * 或 0 9 * * 1-5。",
                    },
                    "prompt": {
                        "type": "string",
                        "description": "触发时注入给 Agent 的用户请求。",
                    },
                    "recurring": {
                        "type": "boolean",
                        "description": "是否周期性重复触发，默认 true；false 表示一次性任务，首次触发后删除。",
                    },
                    "durable": {
                        "type": "boolean",
                        "description": "是否写入磁盘跨 Agent 重启保留任务定义，默认 true；false 表示仅当前进程有效。",
                    },
                },
                "required": ["cron", "prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_crons",
            "description": "列出当前定时任务，包括 durable 和可选的 session-only 任务。",
            "parameters": {
                "type": "object",
                "properties": {
                    "include_session": {
                        "type": "boolean",
                        "description": "是否包含 session-only 定时任务，默认 true。",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_cron",
            "description": "取消一个定时任务。",
            "parameters": {
                "type": "object",
                "properties": {
                    "cron_id": {"type": "string", "description": "定时任务 ID，例如 cron_000001。"}
                },
                "required": ["cron_id"],
            },
        },
    },
]


from tools_configs.team_configs import TEAM_TOOLS
from tools_configs.worktree_configs import WORKTREE_TOOLS


BASE_TOOLS = (
    BASE_TOOLS
    + SUBAGENT_TOOLS
    + SKILL_TOOLS
    + COMPACT_TOOLS
    + MEMORY_TOOLS
    + TASK_TOOLS
    + BACKGROUND_TOOLS
    + CRON_TOOLS
    + TEAM_TOOLS
    + WORKTREE_TOOLS
)
