"""
tina错误类定义
"""


class TinaError(Exception):
    pass


class TinaWarning(Warning):
    pass


class TinaInfo(UserWarning):
    pass


class ToolNotFound(TinaError):
    def __init__(self, tool_name: str):
        super().__init__(
            f"Tool {tool_name} not found. \n工具 {tool_name}并没有找到，查看是否为拼写错误或者没有注册"
        )


class ToolsAddError(TinaError):
    def __init__(self):
        super().__init__(
            "Error adding Tools: Only objects of the Tools class can be merged. Please ensure both objects are instances of the Tools class.  \n工具合并失败：仅支持将两个Tools类对象进行合并。请检查参与合并的对象是否均为Tools类实例。"
        )


class ToolAlreadyExists(TinaError):
    def __init__(self, message: str):
        super().__init__(message)


class ToolsNotNamed(TinaError):
    def __init__(self):
        super().__init__(
            "Tools not named. Please name your Tools instance. \n工具包没有命名，这会导致无法识别工具归属，删除失效，请在分发你的工具包时指定name参数。"
        )


class ToolParameterError(TinaError):
    def __init__(self, tool_name: str, parameter_name: str, parameter_type: str):
        super().__init__(
            f"{tool_name} parameter {parameter_name} should be {parameter_type}."
        )


class ToolParameterNotFound(TinaError):
    def __init__(self, tool_name: str, parameter_name: str):
        super().__init__(f"{tool_name} parameter {parameter_name} not found.")


class ToolParameterTypeError(TinaError):
    def __init__(
        self, tool_name: str, parameter_name: str, expected_type: str, actual_type: str
    ):
        super().__init__(
            f"{tool_name} parameter {parameter_name} should be {expected_type}, but got {actual_type}."
            "\n工具{tool_name}的参数{parameter_name}应该是{expected_type}类型，但是实际是{actual_type}类型。，请检查参数类型是否正确。"
        )


class NetworkNotConnected(TinaError):
    def __init__(self):
        super().__init__(
            "Network is not connected. Please check your network connection and try again. \n网络未连接，请检查网络连接后重试。"
        )


class APIRequestFailed(TinaError):
    def __init__(self, url: str, status_code: int, error_details: str = ""):
        # 保留结构化字段，方便上层分类（余额不足 / 鉴权失败 / 限流 …）
        self.url = url
        self.status_code = status_code
        self.error_details = error_details
        super().__init__(
            f"API request failed:request {url} failed,\n status code {status_code}.\n {error_details}\nAPI请求失败：请求{url}失败，\n状态码{status_code}。\n{error_details}"
        )


def classify_api_error(error: BaseException) -> dict:
    """把一次 LLM/HTTP 失败归一化为 ``{kind, fatal, message}``。

    - ``kind``: balance / auth / rate_limit / server / transient / unknown
    - ``fatal``: True 表示「不处理就可能一直失败、需要用户介入」（余额、鉴权）；
      False 表示可通过重试/等待恢复。
    - ``message``: 给用户看的中文简述。
    """
    status = getattr(error, "status_code", None)
    details = getattr(error, "error_details", "") or ""
    text = f"{error} {details}".lower()

    if status == 402 or "insufficient balance" in text or "insufficient_quota" in text or "余额不足" in text:
        return {
            "kind": "balance",
            "fatal": True,
            "message": "账户余额不足 / 额度用尽（HTTP 402 Insufficient Balance）",
        }
    if status in (401, 403) or "unauthorized" in text or "invalid api key" in text or "authentication" in text:
        return {
            "kind": "auth",
            "fatal": True,
            "message": f"鉴权失败（HTTP {status or '?'}），请检查 API Key / 权限",
        }
    if status == 429 or "rate limit" in text or "too many requests" in text:
        return {
            "kind": "rate_limit",
            "fatal": False,
            "message": "触发限流（HTTP 429），稍后重试",
        }
    if status is not None and 500 <= status < 600:
        return {
            "kind": "server",
            "fatal": False,
            "message": f"服务端错误（HTTP {status}），可重试",
        }
    if status is not None and status >= 400:
        # 其它 4xx：多半是请求本身有问题（参数/上下文长度等），不重试
        return {
            "kind": "request",
            "fatal": False,
            "message": f"请求被拒（HTTP {status}）：{details or error}",
        }
    return {
        "kind": "unknown",
        "fatal": False,
        "message": str(error).strip() or type(error).__name__,
    }


class ModelPathNotGiven(TinaError):
    def __init__(self, model_name: str):
        super().__init__(
            f"Model path is not given. Please provide a valid model path. \n模型的路径没有给出，请提供一个有效的模型路径。"
        )


class NoConfirmationHandler(TinaError):
    def __init__(self):
        super().__init__(
            "No confirmation handler is given. Please provide a valid confirmation handler. \n你设定了工具需要被确认执行，但是没有设置处理程序，请注册on_tool_confirmation事件"
        )
