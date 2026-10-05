# tina-tui

`tina` 的终端界面扩展，基于 [Textual](https://textual.textualize.io/)。作为独立的发行包 `tina-tui` 维护，不并入 `tina-python` 主包；主包需要时通过 `tina-python[tui]` 安装它。

定位：方便测试你写的 Agent 的交互控制台，也可以直接当作自己的 TUI 使用。

## 安装

```bash
pip install tina-tui
# 或（由主包的可选依赖带入）
pip install tina-python[tui]
```

## 快速开始

```python
from tina import Agent, Tools
from tina.llm import BaseAPI
from tina_tui import run_agent_in_tui

agent = Agent(llm=BaseAPI(), tools=Tools(), name="demo")
run_agent_in_tui(agent, max_tokens=32000)
```

## 数据层可单独使用

渲染数据层 `TuiMessageStore` 与 `TokenCounter` **不依赖 textual**，可以单独导入接入你自己的界面：

```python
from tina_tui import TuiMessageStore, TokenCounter
```

## 说明

- 本包依赖 `tina-python`，使用 `tina` 的 `Agent`、`ContextManager` 等公开 API。
- 完整说明（安装、指令、快捷键、自建界面）见主包仓库的 `docs/tui.md`。
