from typing import Any, Dict, List


class AgentResponse(dict):

    def __init__(self, **kwargs):
        data = {k: v for k, v in kwargs.items() if v is not None}
        super().__init__(data)

    @property
    def role(self) -> str:
        """对话角色"""
        return self.get("role", "")

    @property
    def content(self) -> str:
        """回复内容"""
        return self.get("content", "")

    @property
    def reasoning_content(self) -> str:
        """思考过程（如 DeepSeek R1 的输出）"""
        return self.get("reasoning_content", None)

    @property
    def tool_name(self) -> str:
        return self.get("tool_name", None)

    @property
    def tool_arguments(self) -> Dict[str, Any]:
        return self.get("tool_arguments", None)

    @property
    def tool_calls(self) -> List[Dict[str, Any]]:
        return self.get("tool_calls", None)

    def __setattr__(self, name, value):

        raise AttributeError(
            f"AgentResponse的属性是只读的 请不要修改'{name}'的值通过属性赋值 而是应该使用['{name}'] = {value} "
        )
