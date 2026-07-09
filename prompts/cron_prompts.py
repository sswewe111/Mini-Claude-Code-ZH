CRON_SYSTEM_RULES = """定时任务规则：
- 用户要求“每天/每周/每隔一段时间/定时/提醒/自动检查”时，可以使用 schedule_cron。
- schedule_cron 只创建计划，不表示任务已经执行。
- cron 表达式使用五段式：分钟 小时 日 月 星期。
- 创建任务后要告诉用户 cron_id、cron 表达式、是否 durable、是否 recurring。
- 需要查看或取消定时任务时使用 list_crons 或 cancel_cron。
- 收到 <scheduled_task> 后，把其中 prompt 当作用户在该时间点发来的请求处理。
- 不要声称 Agent 进程关闭后仍能触发 cron；durable 只保留任务定义。
"""
