# 终端界面 TUI（可选扩展）

tina 自带一个基于 [Textual](https://textual.textualize.io/) 的终端界面。它是**可选扩展**，不是核心能力，定位有两层：

1. **测试你自己写的 Agent**：写工具、调提示词、看流式输出和工具调用，比在脚本里 `print` 方便得多；
2. **当作你自己的 TUI 来用**：直接把它作为应用的交互界面，或参照它自建界面。

> 核心不依赖它：不安装 `textual` 也能正常使用 tina；`run_agent_in_cli` 仍是零依赖的轻量方案。

## 安装

```bash
pip install tina-python[tui]
```

## 快速开始

```python
from tina import Agent, Tools
from tina.llm import BaseAPI
from tina.utils.tui import run_agent_in_tui

llm = BaseAPI()          # 读取 tina.env
tools = Tools()
agent = Agent(llm=llm, tools=tools, system_prompt="你是一个有用的助手")

run_agent_in_tui(agent, max_tokens=32000)
```

`run_agent_in_tui` 参数：

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `agent` | `Agent` | 必填 | 要交互的 Agent |
| `max_tokens` | `int \| None` | `None` | 用户设置的最大 token 数，用于进度与超限警告 |
| `reasoning_collapsed` | `bool` | `True` | 推理/工具块默认是否折叠 |
| `auto_confirm` | `bool` | `True` | 是否自动注册工具确认弹条（仅在 Agent 未设置确认处理器时注册） |
| `unlimited_context` | `bool` | `False` | 用 tina 提供的无限制上下文管理器替换 Agent 的（见下） |

### 无限制上下文（`unlimited_context=True`）

Agent 默认的上下文管理器有长度限制：历史超过 `max_context_length`（默认 10 万字符）会丢弃最旧的消息，单条工具结果超过 `max_tool_result_length`（默认 6000 字符）会被截断。本地调试或长任务时，这些限制可能不是你想要的行为。

传入 `unlimited_context=True` 会用 tina 提供的无限制管理器替换掉 Agent 的：

```python
run_agent_in_tui(agent, unlimited_context=True)
```

- 不裁剪历史、不截断工具结果
- 现有历史（含 system）会被接管，不会丢
- 内部调用 `agent.set_context_manager(...)`，会一并同步 `agent.runtime.context_manager` 与 `agent.messages`
- 上下文会持续增长，需自行确认模型窗口足够大

运行中也可以用 `app.install_context_manager(cm)` 随时替换（同样是委托 `agent.set_context_manager`）。

也可以直接使用这些类（`from tina.utils.tui import ...`）：

| 名称 | 说明 |
| --- | --- |
| `UnlimitedContextManager` | 无限制的文本上下文管理器 |
| `UnlimitedMultimodalContextManager` | 无限制的多模态上下文管理器 |
| `make_unlimited_context_manager(agent)` | 按 Agent 现有类型构造无限制版并接管历史 |

## 特性

- **流式渲染**：助手正文以 Markdown 流式显示；消费与渲染解耦（定时渲染泵），极快或极长的输出都不掉帧
- **可折叠**：推理内容（`reasoning_content`）与工具调用卡片均可折叠
- **工具确认**：`require_confirmation=True` 的工具会弹出内联选择条（`允许一次` / `始终允许此工具` / `拒绝`），拒绝会以红色提示「工具「x」被用户拒绝使用」；多个工具并发确认会逐个弹出，参数过长时只显示提示（按 `Ctrl+O` 弹窗查看完整参数）
- **打断**：`Esc` 打断本轮回复；已生成的部分正文写回上下文，进行中的工具调用记为「该次调用被打断」，Agent 状态复位
- **token 占用**：显示当前上下文 token 占用与百分比，≥80% 变黄、超限变红；运行时状态栏显示动画
- **多行输入**：支持粘贴多行；`Enter` 发送、`Shift+Enter` / `Alt+Enter` 换行
- **命令补全**：输入 `#` 显示候选，`Tab` 循环补全
- **粘性滚动**：在底部时自动跟随输出；向上滚动查看历史时不打扰；滚回底部自动恢复

## 指令

| 指令 | 别名 | 功能 |
| --- | --- | --- |
| `#help` | `#?` `#h` | 查看可用命令 |
| `#tools` | | 查看当前工具、描述与参数列表 |
| `#context` | | 查看当前上下文（消息块摘要） |
| `#model` | | 查看当前模型信息（model / base_url） |
| `#tokens` | | 查看当前上下文 token 占用（total / prompt / completion / 占比） |
| `#compact` | `#compress` `#summary` | 压缩上下文：让 Agent 自我总结，并写入 system 后清空其余消息 |
| `#clear` | | 清空上下文与界面 |
| `#exit` | `#quit` | 退出 |

## 快捷键

| 快捷键 | 功能 |
| --- | --- |
| `Enter` | 发送 |
| `Shift+Enter` / `Alt+Enter` | 换行 |
| `Tab` | 补全 `#` 命令 |
| `Ctrl+↑` / `Ctrl+↓` | 上一条 / 下一条消息 |
| `Ctrl+Home` / `Ctrl+End` | 第一条 / 最后一条消息 |
| `Ctrl+R` | 折叠 / 展开所有思考块 |
| `Ctrl+T` | 折叠 / 展开所有工具与结果块 |
| `Ctrl+L` | 清空界面 |
| `Ctrl+O` | 确认工具时，弹窗查看完整参数 |
| `Esc` | 有参数弹窗/工具确认时关闭；否则打断本轮回复 |

## 用作你自己的 TUI

界面层与数据层是分开的，`TuiMessageStore`（渲染块列表）和 `TokenCounter`（token 计数）**不依赖 textual**，可以单独导入：

```python
from tina.utils.tui import TuiMessageStore, TokenCounter

store = TuiMessageStore()
counter = TokenCounter(max_tokens=32000)

store.add_user("你好")
for chunk in agent.predict(instruction="你好"):
    block = store.handle_chunk(chunk)     # 把流式分片聚合成渲染块
    counter.add_from_chunk(chunk)         # 记录本次请求的上下文占用
    # 在这里刷新你自己的界面

for block in store.get_blocks():
    print(block.role, block.status, block.content)
```

渲染块类型（`block.role`）：`user` / `assistant` / `reasoning` / `tool` / `result` / `error` / `system`。

也可以继承 `TinaTUI` 自定义界面：

```python
from tina.utils.tui.tui import TinaTUI, run_agent_in_tui

class MyTUI(TinaTUI):
    CSS = TinaTUI.CSS + """
    Screen { background: #10141a; }
    """
```

## 已知限制

- 推理内容与思考链的处理依赖**流式输出**；非流式路径不会通过事件派发 `reasoning_content`。
- `TokenCounter` 记录的是**最近一次请求**返回的 `usage`（当前上下文占用），不是历史累计消耗；因为每次请求都发送全量消息，服务端返回的 total 即当前占用。
- 未设置 `max_tokens` 时，token 只显示占用值，不显示百分比。
- 打断只能停止等待：已经在后台线程里执行的工具本体不会立即终止（副作用无法撤销），但上下文会把该次调用记为「该次调用被打断」，Agent 状态会复位，可继续下一轮。
- 界面用定时渲染泵驱动更新（默认 0.1s 一次），流式正文约每秒刷新数次；内容越长节流间隔越大。
- 界面基于 Textual，版本迭代较快；升级后建议跑一遍 TUI 相关测试。
