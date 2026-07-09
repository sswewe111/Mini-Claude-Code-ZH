BACKGROUND_SYSTEM_RULES = """后台任务规则：
- 预计耗时较长的命令可以设置 bash.run_in_background=true，例如安装依赖、运行完整测试、构建、部署、docker build。
- 后台任务启动后不要声称已经完成，只能说已启动并记录 bg_id。
- 后台任务完成通知会以 <task_notification> 注入；看到通知后再根据 exit_code 和 summary 判断成功或失败。
- 需要主动查看后台任务时调用 background_list 或 background_get。
- 不要把快速命令放后台，例如 pwd、ls、git status、读取小文件。
"""
