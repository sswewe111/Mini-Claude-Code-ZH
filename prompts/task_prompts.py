TASK_SYSTEM_RULES = """持久任务规则：
- 大目标、跨会话目标、可并行目标或用户明确要求“拆任务/持久化/多人协作”时，优先使用 task_create 建立持久任务图。
- task 是跨会话工作看板；todo 是当前会话执行计划。不要把 todo 当作持久任务，也不要为简单一次性请求创建 task。
- 认领任务前先确认依赖已完成。被 blocked_by 阻塞的任务不能开始。
- 开始执行某个持久任务前调用 task_claim；完成后调用 task_complete。
- task_get 用于恢复完整任务说明；task_list 只用于看板摘要。
- 子 Agent 工具 task 和持久 Task System 不是同一个概念：task 工具是临时委托，task_create/task_claim/task_complete 管持久任务图。
"""
