# LocalModelUsingLlamaCpp.py
# 编写者：王出日
# 日期：2025年10月23日
# 描述：本地 llama.cpp 模型调用类，自动管理 llama-server 生命周期

import os
import shutil
import subprocess
import atexit
import signal
import time
from pathlib import Path
from typing import Union, Generator, Optional, List, Dict, Any
import httpx
import json

from .BaseAPI import BaseAPI



class LocalModelUsingLlamaCpp(BaseAPI):
    """
    本地 llama.cpp 模型调用类，自动启动并管理 llama-server 进程
    完全兼容 OpenAI API 格式，无需 API key
    """

    def __init__(
        self,
        model_path: str,
        server_executable: str = "llama-server",
        host: str = "127.0.0.1",
        port: int = 8080,
        ctx_size: int = 8192,
        n_gpu_layers: int = 999,
        use_vulkan: bool = True,
        chat_template: Optional[str] = "qwen",
        server_timeout: int = 30,
        name: Optional[str] = None,
        role: str = "user",
        auto_start: bool = True,
    ):
        """
        初始化本地 llama.cpp 模型
        
        Args:
            model_path (str): GGUF 模型文件路径（必须）
            server_executable (str): llama-server 可执行文件路径，默认 "llama-server"
            host (str): 服务器监听地址，默认 "127.0.0.1"
            port (int): 服务器端口，默认 8080
            ctx_size (int): 上下文长度，默认 8192
            n_gpu_layers (int): GPU 卸载层数，默认 999（全部）
            use_vulkan (bool): 是否启用 Vulkan 后端，默认 True
            chat_template (str): 聊天模板，如 "qwen"、"llama3" 等
            server_timeout (int): 等待服务器启动的超时时间（秒）
            name (str): 模型名称（用于标识）
            role (str): 默认角色
            auto_start (bool): 是否自动启动服务器
        """
        self.model_path = Path(model_path).resolve()
        if not self.model_path.exists():
            raise FileNotFoundError(f"模型文件不存在: {self.model_path}")

        self.server_executable = Path(server_executable).resolve()
        if not self.server_executable.exists():
            # 尝试在 PATH 中查找
            if not shutil.which(server_executable):
                raise FileNotFoundError(f"llama-server 可执行文件不存在: {server_executable}")
            self.server_executable = server_executable

        self.host = host
        self.port = port
        self.ctx_size = ctx_size
        self.n_gpu_layers = n_gpu_layers
        self.use_vulkan = use_vulkan
        self.chat_template = chat_template
        self.server_timeout = server_timeout
        self._server_process = None

        # 设置 BaseAPI 所需属性（无需 API key）
        self.api_key = "local"  # 虚拟 key
        self.base_url = f"http://{host}:{port}/v1/chat/completions"
        self.model = name or self.model_path.stem
        self.MAX_INPUT = ctx_size
        self.temperature = 1.0

        self.token = 0
        self.token_list = []
        self._call = "Local Llama.cpp"
        self._name = name
        self._role = role

        if auto_start:
            self._start_server()

        # 注册退出清理
        atexit.register(self._stop_server)

    def _start_server(self):
        """启动 llama-server 进程"""
        if self._server_process is not None:
            return

        cmd = [
            str(self.server_executable),
            "-m", str(self.model_path),
            "--port", str(self.port),
            "--ctx-size", str(self.ctx_size),
            "--n-gpu-layers", str(self.n_gpu_layers),
        ]

        # if self.use_vulkan:
        #     cmd.append("--vulkan")
        # if self.chat_template:
        #     cmd.extend(["--chat-template", self.chat_template])

        # 隐藏子进程窗口（Windows）
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        self._server_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            startupinfo=startupinfo,
        )

        # 等待服务器启动
        self._wait_for_server()

    def _wait_for_server(self):
        """等待服务器启动完成"""
        start_time = time.time()
        while time.time() - start_time < self.server_timeout:
            try:
                with httpx.Client(timeout=2) as client:
                    response = client.get(f"http://{self.host}:{self.port}/health")
                    if response.status_code == 200:
                        return
            except (httpx.ConnectError, httpx.ReadTimeout):
                time.sleep(0.5)
        raise RuntimeError(f"llama-server 未能在 {self.server_timeout} 秒内启动")

    def _stop_server(self):
        """停止 llama-server 进程"""
        if self._server_process and self._server_process.poll() is None:
            if os.name == 'nt':
                self._server_process.terminate()
            else:
                self._server_process.send_signal(signal.SIGINT)
            try:
                self._server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._server_process.kill()

    def _prepare_headers(self) -> dict:
        """本地模型无需认证头"""
        return {"Content-Type": "application/json"}

    def get_models(self) -> dict:
        """返回当前模型信息"""
        return {
            "current_model": self.model,
            "available_models": [self.model]
        }

    def predictNoStream(
        self,
        input_text: str = None,
        sys_prompt: str = '你的工作非常的出色！',
        role: str = 'user',
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
        **kwargs
    ) -> dict:
        """非流式预测（覆盖 BaseAPI 方法以移除 API key 依赖）"""
        messages = self._prepare_messages(input_text, role, sys_prompt, messages)
        payload = self._prepare_payload(
            messages, temperature, top_p, False, format, json_format, tools,
            top_k, min_p, max_tokens, presence_penalty, frequency_penalty, **kwargs
        )
        headers = self._prepare_headers()

        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(self.base_url, json=payload, headers=headers)
                if response.status_code != 200:
                    raise Exception(f"请求失败: {response.status_code} - {response.text}")
                
                response_data = response.json()
                # 本地 llama.cpp 可能不返回 usage，跳过 token 统计
                result = {
                    "role": "assistant",
                    "content": response_data["choices"][0]["message"]["content"]
                }
                
                if "tool_calls" in response_data["choices"][0]["message"]:
                    tool_calls = response_data["choices"][0]["message"]["tool_calls"]
                    if tool_calls:
                        result["tool_calls"] = tool_calls[0]  # 取第一个
                
                return result
        except Exception as e:
            raise Exception(f"本地模型调用失败: {str(e)}")

    def predictStream(
        self,
        input_text: str = None,
        role: str = 'user',
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
        **kwargs
    ) -> Generator[dict, None, None]:
        """流式预测（需实现 SSE 解析）"""
        messages = self._prepare_messages(input_text, role, sys_prompt, messages)
        payload = self._prepare_payload(
            messages, temperature, top_p, True, format, json_format, tools,
            top_k, min_p, max_tokens, presence_penalty, frequency_penalty, **kwargs
        )
        headers = self._prepare_headers()

        def stream_generator():
            tool_calls_buffer = {}
            with httpx.stream("POST", self.base_url, json=payload, headers=headers, timeout=timeout) as response:
                if response.status_code != 200:
                    raise Exception(f"流式请求失败: {response.status_code}")
                
                for line in response.iter_lines():
                    line = line.strip()
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            if data.get("choices"):
                                delta = data["choices"][0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    yield {"role": "assistant", "content": content}
                                
                                # 工具调用处理（简化版）
                                if "tool_calls" in delta:
                                    for tool_call in delta["tool_calls"]:
                                        index = tool_call.get("index", 0)
                                        if index not in tool_calls_buffer:
                                            tool_calls_buffer[index] = {
                                                "function": {"arguments": ""}
                                            }
                                        if "function" in tool_call:
                                            func = tool_call["function"]
                                            if "name" in func:
                                                tool_calls_buffer[index]["function"]["name"] = func["name"]
                                            if "arguments" in func:
                                                tool_calls_buffer[index]["function"]["arguments"] += func["arguments"]
                        except json.JSONDecodeError:
                            continue
                
                # 最终工具调用
                if tool_calls_buffer:
                    final_tool = list(tool_calls_buffer.values())[0]
                    yield {"role": "assistant", "tool_calls": final_tool}

        return stream_generator()

    def __del__(self):
        """析构时清理服务器"""
        self._stop_server()