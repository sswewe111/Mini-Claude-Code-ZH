import os
from pathlib import Path

from handlers.dispatcher import dispatch_tool_call
from managers.compact_manager import COMPACT_MANAGER
from managers.cron_manager import CRON_MANAGER
from managers.memory_manager import MEMORY_MANAGER
from managers.team_manager import TEAM_MANAGER
from managers.recovery_manager import RecoveryManager
from managers.system_prompt_builder import build_main_system_prompt
from model_client import create_model
from state.agent_state import LoopState, ToolRuntimeContext
from state.hook_state import HookContext
from tools_configs import BASE_TOOLS
from hooks.hook_manager import get_default_hook_manager
from utils.config_handler import compact_config, cron_config
from utils.logger_handler import logger
from utils.normalize_messages import normalize_messages


WORKDIR = Path.cwd()
from dotenv import load_dotenv
load_dotenv(override=True)




def build_model():
    """集中创建 OpenAI 客户端，避免工具函数各自读取 .env。"""
    base_url = os.getenv("ANTHROPIC_BASE_URL")
    api_key = os.getenv("ANTHROPIC_AUTH_TOKEN")
    model_id = os.getenv("MODEL_ID")
    return create_model(base_url=base_url, api_key=api_key), model_id


def _assistant_to_message(message) -> dict:
    assistant_record = {
        "role": "assistant",
        "content": message.content or "",
    }
    if message.tool_calls:
        # OpenAI SDK 返回对象不能直接放入 messages，需要转成普通 dict。
        assistant_record["tool_calls"] = [
            tool_call.model_dump() if hasattr(tool_call, "model_dump") else tool_call
            for tool_call in message.tool_calls
        ]
    return assistant_record


def _max_output_tokens() -> int:
    """读取模型最大输出 token；优先使用环境变量，便于临时调试。"""
    return int(os.getenv("MAX_OUTPUT_TOKENS") or compact_config.get("MAX_OUTPUT_TOKENS", 2048))


def agent_loop(state: LoopState, client, model_id: str, hook_manager=None) -> str:
    """最小 Agent 循环：模型可以反复调用工具，直到产出最终回答。"""
    hook_manager = hook_manager or get_default_hook_manager()
    recovery_manager = RecoveryManager()
    while True:
        state.turn_count += 1
        logger.info("开始第 %s 轮 Agent 循环", state.turn_count)
        active_model_id = recovery_manager.state.current_model_id or model_id

        hook_manager.run_hooks(
            "BeforeModelCall",
            HookContext(
                event="BeforeModelCall",
                messages=state.messages,
                model_id=active_model_id,
                metadata={
                    "turn_count": state.turn_count,
                    "client": client,
                    "compact_manager": COMPACT_MANAGER,
                    "memory_manager": MEMORY_MANAGER,
                    "subagent_depth": 0,
                },
            ),
        )


        # 调用模型前统一规范化消息，保证 tool call 和 tool result 顺序合法。
        def build_messages():
            return normalize_messages([
                {"role": "system", "content": build_main_system_prompt(str(WORKDIR))},
                *state.messages,
            ])

        response = recovery_manager.create_chat_completion(
            client=client,
            model_id=model_id,
            build_messages=build_messages,
            tools=BASE_TOOLS,
            tool_choice="auto",
            max_tokens=_max_output_tokens(),
            compact_manager=COMPACT_MANAGER,
            state_messages=state.messages,
        )
        assistant_message = response.choices[0].message
        assistant_record = _assistant_to_message(assistant_message)
        state.messages.append(assistant_record)

        finish_reason = response.choices[0].finish_reason
        tool_calls = assistant_message.tool_calls or []
        tool_names = [tool_call.function.name for tool_call in tool_calls]
        tool_call_count = len(tool_calls)
        hook_manager.run_hooks(
            "AfterModelCall",
            HookContext(
                event="AfterModelCall",
                messages=state.messages,
                model_id=recovery_manager.state.current_model_id or model_id,
                metadata={
                    "turn_count": state.turn_count,
                    "finish_reason": finish_reason,
                    "tool_call_count": tool_call_count,
                    "tool_names": tool_names,
                },
            ),
        )

        continuation_message = recovery_manager.build_continuation_message(finish_reason)
        if continuation_message:
            state.messages.append(continuation_message)
            continue

        if not assistant_message.tool_calls:
            hook_manager.run_hooks(
                "Stop",
                HookContext(
                    event="Stop",
                    messages=state.messages,
                    model_id=recovery_manager.state.current_model_id or model_id,
                    metadata={
                        "turn_count": state.turn_count,
                        "client": client,
                        "memory_manager": MEMORY_MANAGER,
                        "subagent_depth": 0,
                    },
                ),
            )
            logger.info("Agent 循环结束")
            return assistant_message.content or ""

        for tool_call in assistant_message.tool_calls:
            logger.info("开始执行工具: %s", tool_call.function.name)
            runtime_context = ToolRuntimeContext(
                parent_messages=state.messages,
                client=client,
                model_id=recovery_manager.state.current_model_id or model_id,
                hook_manager=hook_manager,
                workdir=str(WORKDIR),
                compact_manager=COMPACT_MANAGER,
                memory_manager=MEMORY_MANAGER,
            )
            result = dispatch_tool_call(
                tool_call,
                hook_manager=hook_manager,
                runtime_context=runtime_context,
            )
            # 工具结果必须作为 tool 消息写回，模型下一轮才能读取执行结果。
            state.messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })


def run_scheduled_agent_turn(client, model_id: str, hook_manager=None) -> str:
    """消费已触发的 cron 事件，并作为一轮用户请求交给 Agent Loop。"""
    events = CRON_MANAGER.consume_triggered_events(
        limit=cron_config.get("MAX_TRIGGERED_EVENTS_PER_TURN", 5)
    )
    if not events:
        return ""

    message = CRON_MANAGER.format_events_as_user_message(events)
    state = LoopState(messages=[{"role": "user", "content": message}])
    logger.info("开始执行定时任务事件: count=%s", len(events))
    return agent_loop(state, client, model_id, hook_manager=hook_manager)


def main() -> None:
    logger.info("Agent 程序启动")
    hook_manager = get_default_hook_manager()
    hook_manager.run_hooks("SessionStart", HookContext(event="SessionStart"))
    client, model_id = build_model()
    TEAM_MANAGER.start(
        client=client,
        model_id=model_id,
        hook_manager=hook_manager,
        workdir=str(WORKDIR),
    )
    CRON_MANAGER.start(
        client=client,
        model_id=model_id,
        hook_manager=hook_manager,
        workdir=str(WORKDIR),
        runner=run_scheduled_agent_turn,
    )
    # 当前阶段使用固定任务，方便稳定测试工具调用链路。
    # question = "请设计一个计划，请获取当前目录下的所有文件，找到秋天.txt文件，然后用子agent读取这个文件，將里面的内容进行总结，交由主agent并写入data/summary.txt文件中。"
    #question = "请设计一个计划，先获取当前目录下的所有文件，找到春天.pdf文件，然后加载技能读取这个文件，然后读取秋天.txt文件和夏天.txt文件，將读取的三段内容进行总结，交由主agent并写入data/summary_three.txt文件中。"
    #question = "请获取当前目录下的所有文件，找到summary.txt，交由子agent删除。"
    # question = """
    # 请测试持久 Task System，不要修改项目源代码，也不要调用 bash/read_file/write_file/edit_file。

    # 请按顺序完成：
    # 1. 使用 task_create 创建一个大目标拆分后的任务图：
    # - 任务A：设计 Task System 数据模型
    # - 任务B：实现 task_create/task_list/task_get 工具，依赖任务A
    # - 任务C：实现 task_claim/task_complete 工具，依赖任务A
    # - 任务D：编写 Task System 验收说明，依赖任务B和任务C
    # 2. 调用 task_list 展示当前任务看板，确认依赖排序和 blocked/ready 状态。
    # 3. 尝试认领任务D，预期应失败，因为依赖未完成。
    # 4. 认领任务A，owner 使用 main-agent，然后完成任务A。
    # 5. 再次调用 task_list，确认任务B和任务C已解锁。
    # 6. 认领并完成任务B，owner 使用 main-agent。
    # 7. 调用 task_get 查看任务D完整 JSON，确认它仍被任务C阻塞。
    # 8. 最后用中文总结：哪些任务被创建、哪些任务被阻塞、哪些任务被解锁、Task System 是否能持久化到 .tasks/。
    # """
    # question = """
    # 请测试 s13 Background Tasks 功能，不要修改项目源代码，不要调用 write_file/edit_file。

    # 请按顺序完成：
    # 1. 调用 bash 启动一个后台命令，必须设置 run_in_background=true：
    # Windows 环境使用命令：Start-Sleep -Seconds 5; Write-Output "background done"
    # 2. 记录返回的 bg_id，并明确说明这个后台任务只是已启动，还没有完成。
    # 3. 在后台任务运行期间，继续调用 read_file 读取 configs/background_config.yml，证明 Agent 没有阻塞等待后台命令完成。
    # 4. 调用 background_list 查看后台任务状态。
    # 5. 如果还没有收到 <task_notification>，继续进行下一轮等待通知或再次调用 background_list。
    # 6. 收到 <task_notification> 后，调用 background_get 查看对应 bg_id 的详情和输出尾部。
    # 7. 最后用中文总结：
    # - 后台任务 ID 是什么
    # - 启动后是否立即返回
    # - Agent 是否在后台任务运行期间继续执行了 read_file
    # - 是否收到了 <task_notification>
    # - 输出文件路径是什么
    # - background_get 是否能看到 "background done"
    # """
    question = """
请测试 s18 Worktree Isolation 功能。不要修改项目源代码，除非是在 worktree 隔离目录中写入测试文件。请严格按顺序执行。

1. 调用 todo 制定测试计划。

2. 先调用 worktree_list，确认当前 worktree 记录。

3. 调用 task_create 创建两个持久任务：
   - 任务A subject: s18-worktree-写入隔离文件A
     description: 在绑定的 worktree 中创建 data/s18_alice_result.txt，内容写入“alice isolated write ok”。完成后必须调用 task_complete。
     metadata: {"role": "s18 writer"}
   - 任务B subject: s18-worktree-写入隔离文件B
     description: 在绑定的 worktree 中创建 data/s18_bob_result.txt，内容写入“bob isolated write ok”。完成后必须调用 task_complete。
     metadata: {"role": "s18 writer"}

4. 记录任务A和任务B的 task_id。

5. 分别调用 worktree_create：
   - worktree_create(name="s18-alice-wt", task_id=任务A的task_id)
   - worktree_create(name="s18-bob-wt", task_id=任务B的task_id)

6. 调用 task_get 查看任务A和任务B，确认 metadata.worktree 已写入，并且任务状态仍然是 pending。

7. 调用 worktree_list，确认两个 worktree 都存在，状态为 active，并绑定到对应 task_id。

8. 调用 spawn_teammate 创建 s18_alice：
   - name: s18_alice
   - role: s18 writer
   - prompt: 你是 s18 Worktree Isolation 测试 teammate。进入 idle 后自动认领 ready task。认领任务后，如果 <claimed_task> 中包含 worktree 信息，说明你的工具已经在隔离 worktree 目录中执行。请只在隔离目录中创建任务要求的文件，不要修改主工作区。完成后调用 task_complete(task_id=..., owner="s18_alice", summary=...)，然后用 team_send_message(to="lead", msg_type="result", content=...) 汇报你执行的 pwd、写入文件路径和任务完成结果。

9. 调用 spawn_teammate 创建 s18_bob：
   - name: s18_bob
   - role: s18 writer
   - prompt: 你是 s18 Worktree Isolation 测试 teammate。进入 idle 后自动认领 ready task。认领任务后，如果 <claimed_task> 中包含 worktree 信息，说明你的工具已经在隔离 worktree 目录中执行。请只在隔离目录中创建任务要求的文件，不要修改主工作区。完成后调用 task_complete(task_id=..., owner="s18_bob", summary=...)，然后用 team_send_message(to="lead", msg_type="result", content=...) 汇报你执行的 pwd、写入文件路径和任务完成结果。

10. 调用 bash 等待队友自动认领和执行：
    Windows 命令：Start-Sleep -Seconds 20; Write-Output "wait s18 worktree isolation"

11. 调用 task_list，检查两个任务是否被 s18_alice / s18_bob 认领并完成。

12. 调用 team_check_inbox 读取 lead inbox，查看 teammate 的 result 消息。如果 inbox 为空，说明可能已经被 BeforeModelCall hook 注入，请继续后续检查。

13. 分别调用 worktree_status：
    - worktree_status(name="s18-alice-wt")
    - worktree_status(name="s18-bob-wt")
    检查两个 worktree 是否各自有独立改动。

14. 调用 bash 检查主工作区不应出现这些测试文件：
    Windows 命令：
    Test-Path data/s18_alice_result.txt; Test-Path data/s18_bob_result.txt

15. 调用 bash 检查两个 worktree 中应分别存在自己的文件：
    Windows 命令：
    Test-Path .worktrees/s18-alice-wt/data/s18_alice_result.txt; Test-Path .worktrees/s18-bob-wt/data/s18_bob_result.txt

16. 调用 bash 读取 .worktrees/events.jsonl 尾部：
    Windows 命令：Get-Content .worktrees/events.jsonl -Tail 30

17. 最后用中文总结测试结果，必须包含：
    - 是否成功创建并绑定两个 worktree
    - 任务 metadata.worktree 是否正确写入
    - teammate 是否自动认领绑定 worktree 的任务
    - teammate 的 bash/read_file/write_file 是否在隔离目录中执行
    - 主工作区是否没有出现测试文件
    - 两个 worktree 是否各自保留自己的改动
    - .worktrees/events.jsonl 是否记录 create、bind_task、auto_enter
    - 如果 worktree_create 失败，请说明是否因为当前目录不是有效 git 仓库
"""

    state = LoopState(messages=[{"role": "user", "content": question}])
    with CRON_MANAGER.agent_execution():
        answer = agent_loop(state, client, model_id, hook_manager=hook_manager)
    # answer = agent_loop(state, client, model_id, hook_manager=hook_manager)
    print(answer)


if __name__ == "__main__":
    main()
