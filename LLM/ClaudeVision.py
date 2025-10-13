"""
编写者：王出日
日期：2025年1月
版本：0.4.2
描述：Claude Vision API接口类，支持Anthropic Claude多模态模型

Claude Vision特点：
- 支持图像理解和分析
- 强大的视觉推理能力
- 支持多种图像格式（PNG, JPEG, GIF, WebP）
- 图像分辨率最高支持1568×1568像素
"""

from .BaseAPI import BaseAPI_multimodal
import json

class ClaudeVision(BaseAPI_multimodal):
    """
    Claude Vision API类，用于调用Anthropic Claude多模态模型
    
    支持的模型：
    - claude-3-5-sonnet-20241022: 最新最强视觉模型
    - claude-3-opus-20240229: 最强视觉推理模型
    - claude-3-sonnet-20240229: 平衡视觉模型
    - claude-3-haiku-20240307: 快速视觉模型
    
    环境变量配置：
    - ANTHROPIC_API_KEY: Claude API密钥
    - CLAUDE_BASE_URL: API基础URL (默认: https://api.anthropic.com)
    - CLAUDE_MODEL: 默认模型名称
    """
    
    API_ENV_VAR_NAME = "ANTHROPIC_API_KEY"
    BASE_URL = "https://api.anthropic.com/v1/messages"
    
    def __init__(self, api_key: str = None, model: str = "claude-3-5-sonnet-20241022", base_url: str = None):
        """
        初始化Claude Vision API客户端
        
        Args:
            api_key (str, optional): Anthropic API密钥. 默认从环境变量获取
            model (str, optional): 模型名称. 默认 "claude-3-5-sonnet-20241022"
            base_url (str, optional): API基础URL. 默认 "https://api.anthropic.com/v1/messages"
        """
        super().__init__(model=model, api_key=api_key, base_url=base_url)
        
        # Claude特有配置
        self.max_tokens_default = 4096
        self.max_image_size = 1568  # Claude支持的最大图像尺寸
        
    def _prepare_headers(self) -> dict:
        """重写头部准备方法，适配Claude API格式"""
        return {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
        
    def _encode_image(self, image_path: str) -> str:
        """
        重写图像编码方法，添加Claude特有的图像处理
        
        Args:
            image_path (str): 图像文件路径
            
        Returns:
            str: Base64编码的图像数据
        """
        import base64
        from PIL import Image
        import io
        
        # Claude支持的图像格式
        allowed_formats = ['.png', '.jpg', '.jpeg', '.gif', '.webp']
        if not any(image_path.lower().endswith(ext) for ext in allowed_formats):
            raise ValueError(f"不支持的图片格式，Claude支持{', '.join(allowed_formats)}")
            
        try:
            # 检查并调整图像尺寸
            with Image.open(image_path) as img:
                # 如果图像太大，进行压缩
                if max(img.size) > self.max_image_size:
                    ratio = self.max_image_size / max(img.size)
                    new_size = tuple(int(dim * ratio) for dim in img.size)
                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                    
                    # 保存压缩后的图像到内存
                    img_buffer = io.BytesIO()
                    img_format = img.format or 'PNG'
                    img.save(img_buffer, format=img_format)
                    img_data = img_buffer.getvalue()
                else:
                    # 直接读取原文件
                    with open(image_path, "rb") as image_file:
                        img_data = image_file.read()
                        
                return base64.b64encode(img_data).decode('utf-8')
                
        except Exception as e:
            import logging
            logging.error(f"Claude图片处理失败: {str(e)}")
            raise
            
    def _get_media_type(self, image_path: str) -> str:
        """获取图像的MIME类型"""
        extension = image_path.lower().split('.')[-1]
        media_types = {
            'png': 'image/png',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'gif': 'image/gif',
            'webp': 'image/webp'
        }
        return media_types.get(extension, 'image/jpeg')
        
    def _prepare_claude_multimodal_messages(self, input_text: str = None, input_image: str = None,
                                          sys_prompt: str = '你的工作非常出色！', messages: list = None) -> tuple:
        """
        准备Claude特有的多模态消息格式
        
        Claude的图像格式与OpenAI不同，需要特殊处理
        
        Returns:
            tuple: (system_prompt, messages_list)
        """
        if messages is None:
            messages = []
            
            # 构建用户消息内容
            user_content = []
            
            # 添加图像（如果有）
            if input_image:
                user_content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": self._get_media_type(input_image),
                        "data": self._encode_image(input_image)
                    }
                })
                
            # 添加文本（如果有）
            if input_text:
                user_content.append({
                    "type": "text",
                    "text": input_text
                })
                
            if user_content:
                messages.append({"role": "user", "content": user_content})
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
        
    def predictNoStream(self,
                       input_text: str = None,
                       input_image: str = None,
                       sys_prompt: str = '你的工作非常出色！',
                       messages: list = None,
                       temperature: float = 0.3,
                       top_p: float = 0.9,
                       top_k: int = None,
                       min_p: float = None,
                       max_tokens: int = None,
                       presence_penalty: float = None,
                       frequency_penalty: float = None,
                       tools: list = None,
                       timeout: int = 60,
                       **kwargs) -> dict:
        """Claude Vision专用的非流式预测方法"""
        import httpx
        from ..core.error import APIRequestFailed
        
        sys_prompt, messages = self._prepare_claude_multimodal_messages(
            input_text, input_image, sys_prompt, messages
        )
        
        # Claude API特有的格式
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens or self.max_tokens_default,
            "stream": False
        }
        
        # 添加system prompt
        if sys_prompt:
            payload["system"] = sys_prompt
            
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
            
        payload.update(kwargs)
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