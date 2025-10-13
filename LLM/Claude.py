"""
编写者：王出日
日期：2025年1月
版本：0.4.2
描述：Claude API接口类，支持Anthropic Claude系列模型

Claude模型特点：
- 支持长上下文（最高200K tokens）
- 擅长分析、推理、创作任务
- 安全性和有用性平衡良好
- 支持工具调用和JSON模式
"""

from .BaseAPI import BaseAPI

class Claude(BaseAPI):
    """
    Claude API类，用于调用Anthropic Claude系列模型
    
    支持的模型：
    - claude-3-5-sonnet-20241022: 最新最强模型，平衡性能与成本
    - claude-3-5-haiku-20241022: 快速响应模型
    - claude-3-opus-20240229: 最强推理模型
    - claude-3-sonnet-20240229: 平衡模型
    - claude-3-haiku-20240307: 经济型模型
    
    环境变量配置：
    - ANTHROPIC_API_KEY: Claude API密钥
    - CLAUDE_BASE_URL: API基础URL (默认: https://api.anthropic.com)
    - CLAUDE_MODEL: 默认模型名称
    """
    
    API_ENV_VAR_NAME = "ANTHROPIC_API_KEY"
    BASE_URL = "https://api.anthropic.com/v1/messages"
    
    def __init__(self, api_key: str = None, model: str = "claude-3-5-sonnet-20241022", base_url: str = None):
        """
        初始化Claude API客户端
        
        Args:
            api_key (str, optional): Anthropic API密钥. 默认从环境变量获取
            model (str, optional): 模型名称. 默认 "claude-3-5-sonnet-20241022"
            base_url (str, optional): API基础URL. 默认 "https://api.anthropic.com/v1/messages"
        """
        super().__init__(api_key=api_key, model=model, base_url=base_url)
        
        # Claude特有配置
        self.max_tokens_default = 4096  # Claude默认最大输出tokens
        
    def _prepare_headers(self) -> dict:
        """重写头部准备方法，适配Claude API格式"""
        return {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
        
    def _prepare_claude_messages(self, input_text: str = None, sys_prompt: str = '你的工作非常的出色！', 
                                messages: list = None) -> tuple:
        """
        准备Claude特有的消息格式
        
        Claude API要求system prompt单独传递，且不支持system role在messages中
        
        Returns:
            tuple: (system_prompt, messages_list)
        """
        if messages is None:
            messages = []
            if input_text:
                messages.append({"role": "user", "content": input_text})
        else:
            # 过滤掉system消息，Claude的system prompt单独处理
            filtered_messages = []
            for msg in messages:
                if msg.get("role") != "system":
                    filtered_messages.append(msg)
                else:
                    # 如果messages中有system消息，更新sys_prompt
                    sys_prompt = msg.get("content", sys_prompt)
            messages = filtered_messages
            
        return sys_prompt, messages
        
    def _prepare_payload(self, messages: list, temperature: float, top_p: float, stream: bool,
                        format: str = "text", json_format: str = '{}', tools: list = None,
                        top_k: int = None, min_p: float = None, max_tokens: int = None,
                        presence_penalty: float = None, frequency_penalty: float = None,
                        **kwargs) -> dict:
        """重写载荷准备方法，适配Claude API格式"""
        
        # Claude API特有的格式
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens or self.max_tokens_default,
            "stream": stream
        }
        
        # Claude支持的参数
        if temperature is not None:
            payload["temperature"] = temperature
        if top_p is not None:
            payload["top_p"] = top_p
        if top_k is not None:
            payload["top_k"] = top_k
            
        # Claude工具调用格式
        if tools:
            claude_tools = []
            for tool in tools:
                claude_tool = {
                    "name": tool["name"],
                    "description": tool["description"],
                    "input_schema": tool.get("parameters", {})
                }
                claude_tools.append(claude_tool)
            payload["tools"] = claude_tools
            
        # 扩展参数
        payload.update(kwargs)
        return payload
        
    def predictNoStream(self,
                       input_text: str = None,
                       sys_prompt: str = '你的工作非常的出色！',
                       messages: list = None,
                       temperature: float = 1.0,
                       top_p: float = 0.9,
                       top_k: int = None,
                       min_p: float = None,
                       max_tokens: int = None,
                       presence_penalty: float = None,
                       frequency_penalty: float = None,
                       format: str = "text",
                       json_format: str = '{}',
                       tools: list = None,
                       timeout: int = 180,
                       **kwargs) -> dict:
        """Claude专用的非流式预测方法"""
        import httpx
        import json
        from ..core.error import APIRequestFailed
        
        sys_prompt, messages = self._prepare_claude_messages(input_text, sys_prompt, messages)
        payload = self._prepare_payload(
            messages, temperature, top_p, False, format, json_format, tools,
            top_k, min_p, max_tokens, presence_penalty, frequency_penalty, **kwargs
        )
        
        # Claude API需要单独的system参数
        if sys_prompt:
            payload["system"] = sys_prompt
            
        headers = self._prepare_headers()
        
        response = httpx.post(self.base_url, json=payload, headers=headers, timeout=timeout)
        
        if response.status_code != 200:
            rep = response.read()
            error_data = json.loads(rep.decode('utf-8'))
            raise APIRequestFailed(
                url=self.base_url,
                status_code=response.status_code,
                error_details=error_data.get("error", {}).get("message", "Unknown error")
            )
        
        response_data = response.json()
        
        # Claude响应格式转换
        content = ""
        tool_calls = None
        
        for content_block in response_data.get("content", []):
            if content_block["type"] == "text":
                content += content_block["text"]
            elif content_block["type"] == "tool_use":
                tool_calls = {
                    "id": content_block["id"],
                    "function": {
                        "name": content_block["name"],
                        "arguments": json.dumps(content_block["input"])
                    }
                }
        
        result = {"role": "assistant", "content": content}
        if tool_calls:
            result["tool_calls"] = tool_calls
            
        # 更新token计数
        usage = response_data.get("usage", {})
        self.token += usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        
        return result 