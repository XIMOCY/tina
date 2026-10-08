"""``tinacode`` —— 在任意目录启动一个 tina 编码 agent。

用法::

    cd <你的项目>
    tinacode

行为：

- **工作目录 = 你敲命令时所在的目录**：``code_*`` 工具的相对路径都以它为准。
- **会话历史按目录隔离**：存到 ``<cwd>/.tina/chat_sessions/``，
  换个目录就是另一份历史。
- **模型配置**：优先 ``<cwd>/tina.env`` 或 ``<cwd>/.env``；
  没有就用全局 ``~/.tina/tina.env``（放一份，任何目录都能跑）。
- **目录级定制不用改代码**：目录里的 ``.tinacode.md`` / ``AGENTS.md`` /
  ``.tina.md`` 会被 ``CodingContextManager`` 自动读出来注入系统提示，
  用它可以给这个目录的 agent 定规矩。
"""

from __future__ import annotations

import os
from pathlib import Path

from tina import MultimodalAgent
from tina.llm import BaseMultimodalAPI
from tina.utils.coding_context import CodingContextManager
from tina.utils.coding_tools import CodingTools
from tina.utils.deepseek import enable_deepseek_reasoning_tools

from .tui import run_agent_in_tui

#: 全局配置目录（``~/.tina``）：放一份 tina.env 就能在任意目录跑 tinacode
GLOBAL_CONFIG_DIR = Path.home() / ".tina"
#: 按顺序查找的配置文件名
ENV_FILENAMES = ("tina.env", ".env")

_MISSING_ENV_HINT = """\
[tinacode] 没找到模型配置（tina.env / .env）。

  方式一：放在当前目录（只对这一个项目生效）
      {cwd}{sep}tina.env

  方式二：放到全局（推荐，任何目录都能用）
      {home}{sep}.tina{sep}tina.env

  文件内容示例：
      LLM_API_KEY=sk-xxxxxxxxxxxxxxxx
      BASE_URL=https://api.deepseek.com
      MODEL_NAME=deepseek-chat
"""


def find_env_file(root: str) -> str | None:
    """按「当前目录 → 全局 ~/.tina」的顺序找一个可用的配置文件"""
    for base in (Path(root), GLOBAL_CONFIG_DIR):
        for name in ENV_FILENAMES:
            candidate = base / name
            if candidate.is_file():
                return str(candidate)
    return None


def is_deepseek(llm) -> bool:
    """判断当前后端是不是 DeepSeek（思考模式需要回传 reasoning_content）

    先看环境变量 ``TINACODE_REASONING``（``1``/``0`` 强制开关），
    否则按 base_url / model 里有没有 ``deepseek`` 判断。
    """
    override = os.environ.get("TINACODE_REASONING", "").strip().lower()
    if override in ("1", "true", "yes", "on"):
        return True
    if override in ("0", "false", "no", "off"):
        return False
    haystack = f"{getattr(llm, 'base_url', '') or ''} {getattr(llm, 'model', '') or ''}"
    return "deepseek" in haystack.lower()


def build_agent(root: str, env_path: str) -> MultimodalAgent:
    """在 ``root`` 目录里组装一个编码 agent"""
    tools = CodingTools(root=root).get_tools()
    llm = BaseMultimodalAPI(env_path=env_path)
    agent = MultimodalAgent(llm=llm, tools=tools, name="tinacode")
    # 必须在构造之后设置：Agent 构造时会给自己填默认系统提示，
    # 直接传 context_manager 之外的路径会把 CodingContextManager 注入的
    # 项目上下文（AGENTS.md / 目录树）盖掉。
    agent.set_context_manager(CodingContextManager(root=root, tools=tools))
    # DeepSeek 思考模式要求把 reasoning_content 回传，否则多轮之后报 400。
    # 这是 DeepSeek 专有的，别给别的后端塞这个字段。
    if is_deepseek(llm):
        enable_deepseek_reasoning_tools(agent)
    return agent


def main() -> int:
    root = os.getcwd()
    env_path = find_env_file(root)
    if env_path is None:
        print(_MISSING_ENV_HINT.format(cwd=root, home=Path.home(), sep=os.sep))
        return 1

    try:
        agent = build_agent(root, env_path)
    except Exception as error:  # noqa: BLE001 启动期失败要给出人话
        print(f"[tinacode] 初始化失败：{type(error).__name__}: {error}")
        return 1

    run_agent_in_tui(agent, session_root=root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
