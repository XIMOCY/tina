from .client import MCPClient
from ..core import logger
from typing import Dict, Any


class MCPToolExecutor:
    """
    MCP工具执行器，用于执行MCP工具调用
    与tina的AgentExecutor配合使用
    """

    @staticmethod
    def execute_mcp_tool(
        _tool_name: str, _tool_args: Dict[str, Any], mcp_client: MCPClient
    ) -> str:
        """
        执行MCP工具调用

        Args:
            tool_name: 工具名称，格式为"mcp_server_id_tool_name"
            args: 工具参数
            mcp_client: MCP客户端实例

        Returns:
            str: 工具调用结果
        """
        try:
            # 解析工具名称
            server_id, actual_tool_name = MCPToolExecutor._parse_name(_tool_name)

            # 调用MCP工具
            result = mcp_client.call_tool(actual_tool_name, _tool_args, server_id)

            if result["success"]:

                logger.debug(
                    f"MCPToolExecutor - 工具 '{_tool_name}' 执行结果: {result}：参数 {_tool_args}"
                )
                return result["content"]
            else:
                logger.error(
                    f"MCPToolExecutor - 工具'{_tool_name}' 执行错误: {result.get('error', '未知错误')}"
                )
                return f"工具调用失败: {result.get('error', '未知错误')}"

        except Exception as e:
            logger.error(logger.debug(f"MCPToolExecutor - 错误: {str(e)}"))
            return f"执行MCP工具时出错: {str(e)}"

    async def aexecute_mcp_tool(
        _tool_name: str, _tool_args: Dict[str, Any], mcp_client: MCPClient
    ) -> str:
        try:
            server_id, actual_tool_name = MCPToolExecutor._parse_name(_tool_name)
            result = mcp_client.call_tool(actual_tool_name, _tool_args, server_id)
            if result["success"]:
                logger.debug(
                    f"MCPToolExecutor - 工具 '{_tool_name}' 执行结果: {result}：参数 {_tool_args}"
                )
                return result["content"]
            else:
                logger.error(
                    f"MCPToolExecutor - 工具'{_tool_name}' 执行错误: {result.get('error', '未知错误')}"
                )
                return f"工具调用失败: {result.get('error', '未知错误')}"
        except Exception as e:
            logger.error(logger.debug(f"MCPToolExecutor - 错误: {str(e)}"))
            return f"执行MCP工具时出错: {str(e)}"

    @staticmethod
    def _parse_name(_tool_name: str) -> tuple[str, str]:
        parts = _tool_name.split("_", 2)
        if len(parts) != 3 or parts[0] != "mcp":
            return f"无效的MCP工具名称: {_tool_name}", False

        server_id = parts[1]
        actual_tool_name = parts[2]

        return server_id, actual_tool_name
