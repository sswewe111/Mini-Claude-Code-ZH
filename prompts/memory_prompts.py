MEMORY_SYSTEM_RULES = """长期记忆使用规则：
- Memory 只保存跨会话仍然有价值的信息，例如用户偏好、协作反馈、项目背景、外部资源入口。
- Memory 可能过期。使用涉及文件、函数、配置、外部系统状态的记忆前，应结合当前项目状态验证。
- 不要把临时任务状态、当前 Todo、短期计划、API Key、token、密码、凭据写入 Memory。
- 不要把可通过读取当前代码、README、Git 历史直接得到的信息重复写入 Memory。
- private memory 只代表当前用户偏好；team memory 才能代表项目或团队共识。
- 当用户明确要求“记住”某个长期有效信息时，调用 save_memory。
- 当用户明确要求“忘记”或指出某条记忆错误/过时时，调用 forget_memory 或保存更新后的替代记忆。
"""


MEMORY_READ_ONLY_RULES = """长期记忆只读规则：
- Memory 只作为当前任务的参考上下文。
- Memory 可能过期。使用涉及文件、函数、配置、外部系统状态的记忆前，应结合当前项目状态验证。
- 不要写入、删除或修改长期记忆。
- 如果发现记忆可能过时，只在最终结果中简短说明，不要尝试调用 Memory 写入工具。
"""


MEMORY_RELEVANCE_HEADER = "以下是与当前任务可能相关的长期记忆。必要时使用它们，但如果和当前文件状态冲突，以当前文件状态为准。"


MEMORY_RELEVANCE_PROMPT = """你是 Memory 召回选择器。请根据当前任务和最近对话，从候选长期记忆目录中选择真正相关的文件名。

规则：
- 最多选择 5 个文件。
- 只根据候选目录中的 filename 选择，不要编造文件名。
- 不确定就不要选。
- 如果没有相关记忆，返回 []。
- 只返回 JSON 字符串数组，不要输出额外文字。

输出示例：
["user-is-article-reader.md", "project-release-rule.md"]
"""


MEMORY_EXTRACT_PROMPT = """你是 Memory 提取器。请只根据最近对话，提取未来跨会话仍然有价值的信息。

只提取以下类型：
- user：用户身份、背景、长期偏好，scope 必须是 private。
- feedback：用户对 Agent 工作方式的纠正或确认，默认 private；明确项目级规则才用 team。
- project：项目目标、背景、决策、外部约束，倾向 team；相对日期必须改写为绝对日期。
- reference：外部资源入口或查找线索，通常 team。

不要提取：
- 当前 Todo、短期计划、临时进度。
- API Key、token、密码、凭据。
- 可由代码、README、Git 历史直接得到的信息。
- 只对当前代码版本成立的调试步骤。

请返回 JSON 数组，不要输出额外文字。数组元素格式：
{
  "name": "短横线命名",
  "scope": "private 或 team",
  "type": "user / feedback / project / reference",
  "description": "一行中文描述",
  "content": "Markdown 正文。feedback/project 建议包含 Why 和 How to apply。"
}

如果没有值得保存的新记忆，返回 []。
"""


MEMORY_DREAM_PROMPT = """你是 Memory 整理器。请合并重复记忆、删除过时或互相矛盾的记忆，并保持索引描述简短。
输出 JSON 数组，字段与 Memory 提取器一致。不要输出额外文字。
"""
