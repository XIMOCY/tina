"""
tina.agent.state 的 Docstring
监控Agent的运行状态
"""

from enum import Enum


class AgentState(str, Enum):
    IDLE = "idle"  # 待机
    RESPONDING = "responding"  # 输出中
    THINKING = "thinking"  # 思考
    ON_TOOL_CONFIRM = "on_tool_confirm"  # 等待工具调用确认
    TOOL_CALLING = "tool_calling"  # 工具执行中
    ERROR = "error"  # 错误
