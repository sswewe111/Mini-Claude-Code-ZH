from managers.worktree_manager import WORKTREE_MANAGER


def handle_worktree_create(args: dict) -> str:
    return WORKTREE_MANAGER.create(
        name=args["name"],
        task_id=args.get("task_id", ""),
        base_ref=args.get("base_ref", ""),
    )


def handle_worktree_bind(args: dict) -> str:
    return WORKTREE_MANAGER.bind_task(
        task_id=args["task_id"],
        name=args["name"],
    )


def handle_worktree_list(args: dict) -> str:
    return WORKTREE_MANAGER.list_all(
        include_removed=args.get("include_removed", False),
    )


def handle_worktree_status(args: dict) -> str:
    return WORKTREE_MANAGER.status(args["name"])


def handle_worktree_keep(args: dict) -> str:
    return WORKTREE_MANAGER.keep(
        name=args["name"],
        reason=args.get("reason", ""),
    )


def handle_worktree_remove(args: dict) -> str:
    return WORKTREE_MANAGER.remove(
        name=args["name"],
        discard_changes=args.get("discard_changes", False),
    )


WORKTREE_HANDLERS = {
    "worktree_create": handle_worktree_create,
    "worktree_bind": handle_worktree_bind,
    "worktree_list": handle_worktree_list,
    "worktree_status": handle_worktree_status,
    "worktree_keep": handle_worktree_keep,
    "worktree_remove": handle_worktree_remove,
}
