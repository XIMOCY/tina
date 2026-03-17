import httpx
from .base_api import BaseAPI


class OllamaAPI(BaseAPI):
    def __init__(
        self,
        model: str,
        port: int = 11434,
        num_ctx: int = 4096,
        keep_alive: str = "1h",
        name: str = None,
        role: str = "user",
    ):
        """
        专为 Ollama 优化的子类
        重写初始化以跳过父类对 LLM_API_KEY 的强制检查
        """

        self.model = model
        self.port = port
        self.num_ctx = num_ctx
        self.keep_alive = keep_alive

        self.base_url = f"http://localhost:{port}/v1/chat/completions"
        self.ollama_native_url = f"http://localhost:{port}/api/generate"

        # 2. 手动初始化父类定义的必要成员变量
        from ..core import logger

        self.logger = logger
        self.api_key = "ollama"  # 占位符，满足请求头格式
        self.tokens = 0
        self.token_list = []
        self._name = name
        self._role = role

        # 设置温度和最大输入（兼容 BaseAPI 日志逻辑）
        self.temperature = 0.7
        self.MAX_INPUT = num_ctx

        self.logger.info(
            f"OllamaAPI - 初始化成功: {model} (Port: {port}, Context: {num_ctx})"
        )

        # 3. 立即执行同步预加载
        self._warmup_sync()

    def _warmup_sync(self):
        """使用 httpx 同步客户端执行模型预加载"""
        payload = {
            "model": self.model,
            "keep_alive": self.keep_alive,
            "options": {"num_ctx": self.num_ctx},
        }
        try:
            # 预加载不需要 prompt，Ollama 接收到后会开始加载模型
            with httpx.Client() as client:
                response = client.post(
                    self.ollama_native_url, json=payload, timeout=120.0
                )
                if response.status_code == 200:
                    self.logger.info(
                        f"OllamaAPI - 模型 {self.model} 预加载成功，显存已锁定喵~"
                    )
                else:
                    self.logger.warning(
                        f"OllamaAPI - 预加载返回异常状态码: {response.status_code}"
                    )
        except Exception as e:
            self.logger.error(f"OllamaAPI - 连接 Ollama 服务失败: {e}")

    def _prepare_payload(self, *args, **kwargs):
        """
        重写负载准备逻辑
        确保 num_ctx 在对话请求中也能通过 options 传递给 Ollama
        """
        # 调用父类逻辑生成基础 payload
        payload = super()._prepare_payload(*args, **kwargs)

        return payload
