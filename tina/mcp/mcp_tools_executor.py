import asyncio
import concurrent.futures

from .client import MCPClient
from ..core import logger
from typing import Dict, Any


def _content_to_text(result: Dict[str, Any]) -> str:
    """将 MCP 返回的 TextContent 列表拼接为纯文本"""
    parts = []
    for item in result.get("content") or []:
        text = getattr(item, "text", None)
        parts.append(text if text is not None else str(item))
    return "\n".join(parts)


class MCPToolExecutor:
    """
    MCP工具执行器，用于执行MCP工具调用
    与tina的AgentExecutor配合使用
    """

    @staticmethod
    def execute_mcp_tool(
        _tool_name: str,
        _tool_args: Dict[str, Any],
        mcp_client: MCPClient,
        timeout: float = 60,
    ) -> str:
        """
        执行MCP工具调用（同步）

        Args:
            tool_name: 工具名称，格式为"mcp_server_id_tool_name"
            args: 工具参数
            mcp_client: MCP客户端实例
            timeout: 超时时间（秒），<0 表示不限制

        Returns:
            str: 工具调用结果
        """
        try:
            # 解析工具名称
            server_id, actual_tool_name = MCPToolExecutor._parse_name(_tool_name)

            # 调用MCP工具
            result = mcp_client.call_tool(
                actual_tool_name, _tool_args, server_id, timeout=timeout
            )

            return MCPToolExecutor._format_result(_tool_name, result, _tool_args)

        except concurrent.futures.TimeoutError:
            return f"工具执行超时（{timeout}秒）: {_tool_name}"
        except Exception as e:
            logger.error(f"MCPToolExecutor - 错误: {str(e)}")
            return f"执行MCP工具时出错: {str(e)}"

    async def aexecute_mcp_tool(
        _tool_name: str,
        _tool_args: Dict[str, Any],
        mcp_client: MCPClient,
        timeout: float = 60,
    ) -> str:
        """执行MCP工具调用（异步，不阻塞事件循环）

        MCP 调用体跑在 MCP 专用 loop 上，这里只 await 其 future；超时/打断
        只会取消“等待”，不会卡住 Agent 的事件循环。
        """
        try:
            server_id, actual_tool_name = MCPToolExecutor._parse_name(_tool_name)
            future = mcp_client.submit_tool_call(
                actual_tool_name, _tool_args, server_id
            )
            wait = None if (timeout is None or timeout < 0) else timeout
            result = await asyncio.wait_for(asyncio.wrap_future(future), timeout=wait)
            return MCPToolExecutor._format_result(_tool_name, result, _tool_args)
        except asyncio.TimeoutError:
            return f"工具执行超时（{timeout}秒）: {_tool_name}"
        except Exception as e:
            logger.error(f"MCPToolExecutor - 错误: {str(e)}")
            return f"执行MCP工具时出错: {str(e)}"

    @staticmethod
    def _format_result(
        _tool_name: str, result: Dict[str, Any], _tool_args: Dict[str, Any]
    ) -> str:
        if result["success"]:
            logger.debug(
                f"MCPToolExecutor - 工具 '{_tool_name}' 执行结果: {result}：参数 {_tool_args}"
            )
            return _content_to_text(result)
        logger.error(
            f"MCPToolExecutor - 工具'{_tool_name}' 执行错误: {result.get('error', '未知错误')}"
        )
        return f"工具调用失败: {result.get('error', '未知错误')}"

    @staticmethod
    def _parse_name(_tool_name: str) -> tuple[str, str]:
        parts = _tool_name.split("_", 2)
        if len(parts) != 3 or parts[0] != "mcp":
            return f"无效的MCP工具名称: {_tool_name}", False

        server_id = parts[1]
        actual_tool_name = parts[2]

        return server_id, actual_tool_name
