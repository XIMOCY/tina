# tina 多 Agent（实验性）

> **实验性功能**：API 可能随版本变动，建议用于原型验证与调试。生产环境请谨慎评估。
>
> 独立发行包 `tina-multi-agent`（import 名 `tina_multi_agent`），不并入 `tina-python` 主包；
> 主包需要时通过 `tina-python[multi-agent]` 安装它。

`tina_multi_agent` 让若干个各自独立的 `Agent`（含 `MultimodalAgent`）注册进一个「环境」，
通过消息总线互相通信，并配一个 Web 调试控制台用于观测与介入。

## 安装

```bash
pip install tina-multi-agent
# 或由主包的可选依赖带入
pip install "tina-python[multi-agent]"
```

Web 调试控制台（FastAPI + WebSocket）已作为本包的核心依赖自带，无需额外安装。

## 文件结构

```
packages/tina-multi-agent/tina_multi_agent/
├── __init__.py          # 导出 Message / MessageBus / MultiAgentEnvironment / MultiAgentWeb
├── message.py           # Message（消息结构）
├── message_bus.py       # MessageBus（队列 + 历史 + 入队监听器）
├── environment.py       # MultiAgentEnvironment（注册、分发、每个 Agent 的收信 worker）
└── web/
    ├── server.py        # MultiAgentWeb（FastAPI：HTTP + WebSocket）
    └── static/index.html
```

## 快速开始

```python
from tina import Agent
from tina.llm import BaseAPI
from tina_multi_agent import MultiAgentEnvironment, MultiAgentWeb

llm = BaseAPI()

env = MultiAgentEnvironment(name="room")
env.add_agent(Agent(llm=llm, name="alice", system_prompt="你是 alice，可用 send_message 和其他 Agent 交流"))
env.add_agent(Agent(llm=llm, name="bob", system_prompt="你是 bob，可用 send_message 和其他 Agent 交流"))

# 方式一：纯 headless
# env.run() 会在 start 后持续运行，直到 env.stop()（异步）
# import asyncio; asyncio.run(env.run())

# 方式二：带 Web 控制台（会自动启动环境）
MultiAgentWeb(env, port=7077).run()
```

启动后：

- 浏览器打开 `http://127.0.0.1:7077` 查看实时对话；
- 或程序内投放指令：
  - `env.predict("开始工作")` —— 广播给所有 Agent；
  - `env.predict("只给 alice", main_agent="alice")` —— 定向给某个 Agent。

Web 控制台所需的 FastAPI / uvicorn / websockets 已随本包自带。

## 核心概念

- **注册**：`env.add_agent(agent, name=None)`，`name` 缺省用 `agent.name`。
- **通信工具**：`start()` 时自动给每个 Agent 注册 `send_message(content, recipient=None)`，
  工具描述里会列出环境内全部 Agent；`recipient` 省略即广播给其他所有 Agent。
- **消息总线**：`env.bus`，一个 `MessageBus`。`put` 入队并记录历史，`history()` 查询，
  `add_listener(fn)` 可订阅「消息入队」事件。
- **收信 worker**：每个 Agent 一个专属收件队列；收到消息、且该 Agent 不在
  `tool_calling` / `on_tool_confirm` / `error` 状态时，把消息注入其上下文并触发一次推理：
  - 外部指令 → `add_user_message`；
  - 同伴消息 → `assistant` + `name=发送者`（思考类模型会自动补 `reasoning_content=""`）。
- **回合中途注入**：Agent 正在输出时又来了消息，不会一直等到整个回合结束——环境给每个
  Agent 挂了 `before_llm_call` 处理器（每轮 LLM 调用前触发），在「工具跑完、下一轮 LLM
  之前」这个安全边界把队列里的消息注入上下文，于是下一轮 LLM 就能看到它们。纯文本回合
  没有工具边界，消息会在回合结束后由 worker 起新回合处理。
- **生命周期**：`await env.start()` / `await env.stop()`；`await env.run()` 阻塞运行直到停止。
- **打断**：`env.interrupt(name)` 打断某个 Agent 当前输出，`env.interrupt_all()` 打断全部。
  打断会保留已流出的部分正文、补齐「被打断」的工具结果并复位状态（不会中止该 Agent 的收信循环）。
- **查询**：`env.agents`、`env.agent_names`、`env.history()`。

## Message

```python
Message(sender: str, content: str, recipient: str | None = None, role: str = "assistant")
```

- `recipient=None` 表示广播；
- `role` 为 `"user"`（外部指令）或 `"assistant"`（Agent 之间）。

## Web 控制台

```python
MultiAgentWeb(
    env,
    host="127.0.0.1",
    port=7077,
    tool_confirmation="ask",   # ask | allow | deny
    confirm_timeout=300.0,
).run()
```

页面能力：

- 左侧 Agent 列表（含「全部」）；主区按 Agent 数量自适应网格，可同时看多个 Agent；
- 实时流式输出，推理内容灰显，工具调用渲染成卡片（名称 · 状态 / 参数 / 结果）；
- 总线消息按方向显示：`◀ 发送者`（收到）、`▶ 收件人`（发出）、`指令`（外部）；
- 底部输入框可选「广播」或定向发送；
- 每个 Agent 生成中会在面板右上角显示「■ 打断」，点击即可打断该 Agent 当前输出（等同 TUI 的 Esc）；
- Markdown 正文用内置轻量渲染（零外部依赖）。

对外接口：

- `GET /health` → `{ok, agents, running}`
- `POST /instruction`，body `{"content": str, "main_agent": str|null}` —— 供外部程序注入指令
- `WS /ws` —— 事件：`init / message / chunk / turn_end / interrupted / confirm / confirm_cancel / permissions / error`

## 工具确认与权限

- `require_confirmation=True` 的工具执行前会弹窗确认（TUI 也支持同类机制）。
- 全局策略 `tool_confirmation`：`ask`（默认，弹窗）/ `allow`（全放行）/ `deny`（全拒绝）。
- 弹窗按钮：`允许 / 始终允许 / 拒绝 / 始终拒绝 / 全部允许 / 全部拒绝`。
- 权限表按 **(Agent, 工具)** 记 `allow` / `deny`，**内存态**（重启即清空）。
  header「权限」窗口可可视化调整，支持「应用到所有 Agent」。
- 无前端在线时默认拒绝；确认超时（`confirm_timeout`）同样按拒绝处理。

## 边界与注意事项

- **软约束**：星型拓扑、禁止广播等，需要写进各 Agent 的 `system_prompt`，框架不强制。
- **尚无消息深度上限**：Agent 间广播互聊会指数放大（实测一条广播可瞬间产生上千次推理）。
  建议用提示词约束，或后续加 `Message.depth` 硬边界来兜底。
- **权限内存态**：跨进程/重启不保留。
- **事件归属**：`on_stream_chunk`、`on_turn_end` 等由开发者或 Web 层自行挂载，环境本身不管理事件。
- **思考模型**：`enable_deepseek_reasoning_tools(agent)` 会给 Agent 打 `_reasoning_required` 标记，
  环境据此给注入的同伴消息补 `reasoning_content`，避免 DeepSeek 思考模式报 400。

## 示例

最小用法可直接参考上面的「快速开始」。更完整的示例（5 个 Agent 的演示、星型 QA 集群等）
放在仓库的忽略目录 `little_toy/` 下，**不随 `tina-python` 包发布**。

## 相关集成（可选）

- **opencode**：环境侧工具 `ask_opencode` 通过 opencode server 的**会话 API** 向 opencode 发消息；
  opencode 侧可放自定义工具（`.opencode/tools/ask_qa.ts`）调用本服务的 `POST /instruction` 回投指令。
- **飞书 / Lark**：Agent → 飞书走官方 MCP（`@larksuiteoapi/lark-mcp`）；
  飞书 → Agent 需要机器人事件订阅（建议用长连接 SDK）转发到 `POST /instruction`。
