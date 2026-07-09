from handlers.base_handlers import handle_load_skill
from tools.bash_tools import run_bash
from tools.file_tools import edit_file, read_file, write_file
from utils.config_handler import skill_config


def handle_subagent_bash(args: dict) -> str:
    return run_bash(args["command"])


def handle_subagent_read_file(args: dict) -> str:
    return read_file(args["path"], args.get("limit"))


def handle_subagent_write_file(args: dict) -> str:
    return write_file(args["path"], args["content"])


def handle_subagent_edit_file(args: dict) -> str:
    return edit_file(args["path"], args["old_text"], args["new_text"])


SUBAGENT_HANDLERS = {
    "bash": handle_subagent_bash,
    "read_file": handle_subagent_read_file,
    "write_file": handle_subagent_write_file,
    "edit_file": handle_subagent_edit_file,
}


if skill_config.get("ALLOW_SUBAGENT_LOAD_SKILL", True):
    SUBAGENT_HANDLERS["load_skill"] = handle_load_skill
