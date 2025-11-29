from .Client import MCPClient
from ..agent.core.tools import Tools
from typing import Dict, Any
class MCPToolExecutor:
    """
    MCP工具执行器，用于执行MCP工具调用
    与tina的AgentExecutor配合使用
    """
    
    @staticmethod
    def execute_mcp_tool(tool_name: str, args: Dict[str, Any],tools: Tools, mcp_client: MCPClient) -> tuple:
        """
        执行MCP工具调用
        
        Args:
            tool_name: 工具名称，格式为"mcp_server_id_tool_name"
            args: 工具参数
            mcp_client: MCP客户端实例
        
        Returns:
            tuple: (结果, 是否成功)
        """
        try:
            # 解析工具名称
            parts = tool_name.split('_', 2)
            if len(parts) != 3 or parts[0] != "mcp":
                return f"无效的MCP工具名称: {tool_name}", False
            
            server_id = parts[1]
            actual_tool_name = parts[2]
            
            # 调用MCP工具
            result = mcp_client.callTool(actual_tool_name, args, server_id)

            if result["success"]:
                tool_result = ""
                for text_content in result["content"]:
                    if text_content.type == "text":
                        tool_result += text_content.text
                    
                return tool_result
            else:
                return f"工具调用失败: {result.get('error', '未知错误')}"
        
        except Exception as e:
            return f"执行MCP工具时出错: {str(e)}"