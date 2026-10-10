# 更新日志

本项目遵循[语义化版本](https://semver.org/lang/zh-CN/)。0.x 阶段按「功能 → 次版本、修复 → 修订号」发布。

> **0.x 期间任何版本都可能出现破坏性变更**，一律在本文件里用 ⚠️ 明确标注，并给出替代写法。

---

## [0.7.3] - 2026-10-10

### 修复

- **`MultimodalAgent` 用不了 `file_id`（Files API）**：这是「下游全支持、上游没贯通」的遗漏 ——
  `build_multimodal_message` 和 `MultimodalContextManager.add_user_message` 一直都有
  `input_file_id` / `file_id` 参数，但 `MultimodalAgent` 与
  `ToolCallingMutilemodalAgentRuntime` 只暴露了 `image` / `audio` / `url`，
  参数传到中间层就断了，用户无法通过 `agent.apredict(file_id=...)` 使用 Files API 引用。
  - 现在 `predict` / `apredict` / `apredict_no_stream` 以及 runtime 的四个 prediction
    方法都接受 `file_id`。
  - 新参数**追加在参数表末尾**（`min_p` 之后），老的按位置传参不受影响。
  - 用法：`agent.apredict(instruction="看看这张图", file_id=[fid])`，
    其中 `fid = FilesAPI().upload_cached("a.png")`。
  - 相比内联 base64，`file_id` 在多轮长会话里不必每轮重传图片数据。
- **`FilesAPI.exists()` 对已删除的文件会抛异常**：OpenAI 对不存在的 `file_id` 返回 404，
  但 **DeepSeek 返回 400**（`invalid_request_error: file_id does not exist or is not
  created under your account`，实测）。原实现只认 404，其余一律
  `raise APIRequestFailed` —— 于是「查一下这个文件还在不在」这种最正常的用法会直接炸，
  `delete()` 之后紧跟 `exists()` 就复现。
  - 现在 404、以及「400 + 不存在类文案」都返回 `False`；其他状态码（含**无关的 400**）
    仍然抛异常，不会被吞掉。

### 测试

- 新增 `test/test_multimodal_file_id.py`（14 例）：签名防回归、端到端贯通、多图顺序、
  与 `image` 混用、`_content_length` 对 `file` 块的开销、超长上下文裁剪不崩。
- `test/conftest.py` 的 `MockLLM.apredict` 补上非流式分支（对齐 `BaseAPI.apredict`
  的 `stream=False` 默认值），此前它总是返回 AsyncGenerator。
- `test/test_files_api.py` 新增 3 例：DeepSeek 式 400 not-found 返回 `False`、
  无关 400 仍然抛异常、`_is_missing` 的状态码矩阵。

---

## [0.7.2] - 2026-10-09

### ⚠️ 破坏性变更

- **删除 `tina.utils.system_tools`**（547 行）。这个模块名说的是「系统工具」，内容却几乎全是文件读写与命令执行，语义不准。
  - 替代：`tina.utils.coding_tools.CodingTools`，工具前缀从 `tina_sys_tools_*` 改为 `code_*`
    （`read_code`→`code_read`、`write_code`→`code_write`、`terminal`→`code_bash` 等）
  - 迁移：`from tina.utils.system_tools import system_tools` → `from tina.utils.coding_tools import CodingTools`
- **`tina.llm` 不再导出 `is_file_id`**，`files_api.py` 里的函数本体也一并删除。
  - 迁移：不再需要判断前缀，直接把值传给 `FilesAPI` / 多模态消息的 `file_id` 字段即可。
- **`Agent` / `MultimodalAgent` 的 `system_prompt` 行为变化**：未显式传 `system_prompt` 时，现在会**保留**传入的 `context_manager` 自带的系统提示（以前会被默认提示覆盖）。
  - 影响：`Agent(llm=..., tools=..., context_manager=YourCM())` 这类写法，以前 `YourCM` 的系统提示会静默失效，现在会保留。要显式覆盖仍然传 `system_prompt=`。
- **`TuiMessageStore.snapshot()` 语义修正**：供会话持久化用的「扁平字段快照」改名为 **`dump_snapshot()`**，`snapshot()` 恢复成 0.7.1 的「深拷贝快照（供界面安全遍历）」。
  - 迁移：持久化场景把 `.snapshot()` 改成 `.dump_snapshot()`；`load_snapshot()` 不变。

### 新增

- **`CodingTools`（`tina.utils.coding_tools`）**：主包内置的编码工具包（命名空间 `code`）——
  `code_read` / `code_glob` / `code_grep` / `code_write` / `code_edit` / `code_patch` / `code_bash`。
  重点在可靠的局部编辑（精确匹配 + 唯一性校验 + 原子写）与 unified diff 批量应用。纯标准库实现。
- **`CodingContextManager`（`tina.utils.coding_context`）**：项目感知的上下文管理器，
  自动把 `AGENTS.md` / `.tinacode.md` / `.tina.md`、工作目录与目录结构摘要注入系统提示，
  可用 `refresh_project_context()` 刷新。
- **`tina.utils.session_store`** 从 `tina.utils` 正式导出：`SessionMeta` / `SessionStore` / `ensure_session_dir`。
- **`Agent.refresh_mcp_tools()`**：按当前 MCP 连接重新合并工具；
  `add_mcp_server` / `remove_mcp_server` 会自动调用，动态增删的 MCP 服务其工具立刻可用。
- **`tinacode` 命令**（随 `tina-tui` 安装）：在任意目录直接起一个编码 agent，不用写 Python。
  工作目录 = 你敲命令时所在目录，会话存到 `<cwd>/.tina/chat_sessions/`，
  配置读 `<cwd>/tina.env` 或回退全局 `~/.tina/tina.env`。
- **TUI**：
  - `#export` / `#save` 导出会话为 Markdown；会话快照恢复（保留耗时/timing 等实时状态）
  - `#paste` / `Alt+V` 附加图片（终端吃掉 `Ctrl+V` 时的可靠入口），`#paste 路径.png` 按路径指定
  - `#balance` 显示账户余额与本轮花费（用余额差值估算，无需维护单价表）
  - 状态栏显示 prompt 缓存命中率
  - 忙碌时提交的消息**入队**（显示「排队中」），当前轮次结束后自动发送

### 修复

- **TUI 滚动**：贴底时直写 `scroll_y` 会留下陈旧的 `scroll_target_y`，导致滚轮一档就把视口拽回旧位置
  （长会话下表现为「从上次输入消息的位置跳过去」）。改用 `scroll_to(animate=False)` 同步两者。
- **TUI 窗口化渲染**默认关闭（`TinaTUI.WINDOWED = False`）：真实终端里代价大头是重绘而非布局，
  实测 Windows Terminal 下开启反而更卡；保留为长历史频繁滚动场景的可选项。
- **`Tools(tools_executor=...)` 的可变默认参数**：`ToolsExecutor()` 作为默认值会在所有 `Tools` 实例间共享，
  改为 `None` 再按需构造。
- **`tinacode` 的 DeepSeek 思考模式**：补上 `enable_deepseek_reasoning_tools`，
  否则「思考 + 工具调用」多轮后会报 `The reasoning_content in the thinking mode must be passed back to the API`。
- `from tina.llm import *` 不再因 `__all__` 里残留 `is_file_id` 而抛 `AttributeError`。

---

## [0.7.1] - 2026-10-05

- 同步 README 描述，无代码变更。

## [0.7.0] - 2026-10-0x

- `BASE_URL` 不再需要自带 `/chat/completions`，会自动补全。
- TUI 与多 Agent 环境拆成独立发行包（`tina-tui` / `tina-multi-agent`），主包内仅保留 `tina.utils.*` 兼容转发壳。
