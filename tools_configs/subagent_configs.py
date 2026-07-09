from tools_configs.base_configs import SKILL_TOOLS
from utils.config_handler import skill_config


SUBAGENT_AVAILABLE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "在当前工作目录执行一条命令；Windows 使用 PowerShell，Linux/macOS 使用 bash，并返回 stdout、stderr 和退出码。",
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
]


if skill_config.get("ALLOW_SUBAGENT_LOAD_SKILL", True):
    SUBAGENT_AVAILABLE_TOOLS = SUBAGENT_AVAILABLE_TOOLS + SKILL_TOOLS
