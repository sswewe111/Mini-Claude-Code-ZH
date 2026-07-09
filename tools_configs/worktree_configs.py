WORKTREE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "worktree_create",
            "description": "为任务创建隔离 git worktree，可选绑定 task_id；绑定不会改变任务状态。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "worktree 名称，只能包含字母、数字、点、下划线和短横线。"},
                    "task_id": {"type": "string", "description": "可选，要绑定的持久任务 ID。"},
                    "base_ref": {"type": "string", "description": "可选，创建 worktree 的 git ref，默认 HEAD。"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "worktree_bind",
            "description": "把已有 worktree 绑定到持久任务 metadata.worktree，不认领任务。",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "持久任务 ID。"},
                    "name": {"type": "string", "description": "已有 worktree 名称。"},
                },
                "required": ["task_id", "name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "worktree_list",
            "description": "列出 worktree 记录，包括绑定任务、分支、路径和状态。",
            "parameters": {
                "type": "object",
                "properties": {
                    "include_removed": {"type": "boolean", "description": "是否包含已删除记录，默认 false。"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "worktree_status",
            "description": "查看某个 worktree 的 git status、分支和绑定任务。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "worktree 名称。"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "worktree_keep",
            "description": "保留 worktree 用于人工 review，记录 keep 事件，不删除目录或分支。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "worktree 名称。"},
                    "reason": {"type": "string", "description": "可选，保留原因。"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "worktree_remove",
            "description": "删除 worktree 并清理分支。有未提交改动时默认拒绝；discard_changes=true 表示确认丢弃。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "worktree 名称。"},
                    "discard_changes": {"type": "boolean", "description": "是否确认丢弃 worktree 内未提交改动。"},
                },
                "required": ["name"],
            },
        },
    },
]
