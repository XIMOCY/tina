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

## 特性

- **流式渲染**：助手正文以 Markdown 流式显示
- **可折叠**：推理内容（`reasoning_content`）与工具调用卡片均可折叠
- **工具确认**：`require_confirmation=True` 的工具会弹出内联选择条（`允许一次` / `始终允许此工具` / `拒绝`），拒绝会以红色提示「工具「x」被用户拒绝使用」
- **token 统计**：显示累计进度与百分比，≥80% 变黄、超限变红
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
| `#tokens` | | 查看 token 统计（累计、上下限、占比） |
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
| `Esc` | 取消当前工具确认（等同拒绝） |

## 用作你自己的 TUI

界面层与数据层是分开的，`TuiContextManager`（渲染块列表）和 `TokenCounter`（token 计数）**不依赖 textual**，可以单独导入：

```python
from tina.utils.tui import TuiContextManager, TokenCounter

context = TuiContextManager()
counter = TokenCounter(max_tokens=32000)

context.add_user("你好")
for chunk in agent.predict(instruction="你好"):
    block = context.handle_chunk(chunk)   # 把流式分片聚合成渲染块
    counter.add_from_chunk(chunk)         # 累计 token
    # 在这里刷新你自己的界面

for block in context.get_blocks():
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
- 未设置 `max_tokens` 时，token 只显示累计值，不显示百分比。
- 界面基于 Textual，版本迭代较快；升级后建议跑一遍 TUI 相关测试。
