from typing import Any
from abc import ABC, abstractmethod
from ...utils.multimodal_formatter import build_multimodal_message


class BaseContextManager(ABC):
    messages: list[dict[str, Any]]

    @abstractmethod
    def set_messages(self, messages: list[dict[str, Any]]) -> None:
        pass

    @abstractmethod
    def get_messages(self) -> list[dict[str, Any]]:
        pass

    def add_user_message(self, message: str) -> list[dict[str, Any]]:
        pass

    @abstractmethod
    def add_tool_calls(self, tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
        pass

    @abstractmethod
    def add_tool_calls_result(self, tool_calls_result: list[dict[str, Any]]) -> None:
        pass

    @abstractmethod
    def add_assistant_message(self, message: str) -> list[dict[str, Any]]:
        pass

    @abstractmethod
    def clear_messages(self) -> None:
        pass


class ContextManager(BaseContextManager):
    max_length: int
    max_tool_result_length: int
    tool_calls_result: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]
    messages: list[dict[str, Any]]

    def __init__(
        self, max_length: int = 100000, max_tool_result_length: int = 10000
    ) -> None:
        self.max_length = max_length
        self.max_tool_result_length = max_tool_result_length
        self.tool_calls = []  # 初始化 tool_calls
        self.tool_calls_result = []  # 初始化 tool_calls_result
        self.messages = []  # 初始化 messages，确保每个实例都有独立的列表

    def set_messages(self, messages: list[dict[str, Any]]) -> None:
        self.messages = messages

    def get_messages(self) -> list[dict[str, Any]]:
        """返回消息列表"""
        return self.messages

    def get_system_message(self) -> str:
        """返回系统消息（没有则返回空字符串）"""
        if not self.messages:
            return ""
        first = self.messages[0]
        if first.get("role") == "system":
            return first.get("content", "") or ""
        return ""

    def set_system_message(self, message: str) -> None:
        if not self.messages:  # 如果没有系统消息，则创建一个
            self.messages.append({"role": "system", "content": message})
        else:
            # 如果第一条不是 system，也强制替换为 system
            self.messages[0] = {"role": "system", "content": message}

    def add_user_message(self, message: str) -> list[dict[str, Any]]:
        self.messages.append({"role": "user", "content": message})
        self.limit_messages()
        return self.messages

    def add_tool_calls(self, tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # 给每个 tool_call 补充 tool_call_id

        for tool_call in tool_calls:
            if "tool_call_id" not in tool_call and "id" in tool_call:

                tool_call["tool_call_id"] = tool_call["id"]

        self.tool_calls.extend(tool_calls)

        # assistant 消息中带 tool_calls（content 通常为空）
        self.messages.append(
            {
                "role": "assistant",
                "tool_calls": tool_calls,
                "content": "",
            }
        )
        return tool_calls

    def add_tool_calls_result(self, tool_calls_result: list[dict[str, Any]]) -> None:
        """
        批量追加工具结果。
        要求传进来的每个元素至少包含:
        - "tool_call": 对应的 tool_call（可选）
        - "tool_name": 工具名称（可选）
        - "result": 工具执行结果字符串
        """
        for item in tool_calls_result:
            # 确保有 result 字段

            item["result"] = item.get("content", "") or ""
            item["tool_name"] = item.get("tool_name", None)
            self.tool_calls_result.append(item)

            # 同时追加到 messages 中（作为 tool 消息）
            content = str(item.get("result", ""))
            if len(content) > self.max_tool_result_length:
                content = content[: self.max_tool_result_length - 3] + "..."
            self.messages.append(
                {
                    "role": "tool",
                    "content": content,
                    # 如果有 tool_call_id 就带上，方便对齐
                    "tool_call_id": item.get("tool_call_id"),
                }
            )

        self.limit_messages()

    def add_tool_call_result(
        self, tool_result: str | None, tool_call_id: str, tool_call: dict[str, Any]
    ) -> None:
        if tool_result is None:
            tool_result = ""

        record = {
            "tool_call": tool_call,
            "tool_name": tool_call.get("function", {}).get("name"),
            "result": tool_result,
            "tool_call_id": tool_call_id,
        }
        self.tool_calls_result.append(record)

        # 截断过长的结果再写入 messages
        content = tool_result
        if len(content) > self.max_tool_result_length:
            content = content[: self.max_tool_result_length - 3] + "..."
        self.messages.append(
            {
                "role": "tool",
                "content": content,
                "tool_call_id": tool_call_id,
            }
        )
        self.limit_messages()

    def get_tool_calls(self) -> list[dict[str, Any]]:
        return self.tool_calls

    def get_tools_result(self) -> list[dict[str, Any]]:
        """
        返回“完整的工具结果列表”，
        每个元素是一个 dict，至少包含: tool_call, tool_name, result, tool_call_id。
        """
        return self.tool_calls_result

    def get_tool_result_contents(self) -> list[str]:
        """
        只返回工具结果的纯文本列表: [result1, result2, ...]
        """
        return [str(item.get("result", "")) for item in self.tool_calls_result]

    def add_assistant_message(
        self, message: str, name: str = None
    ) -> list[dict[str, Any]]:

        self.messages.append(
            {"role": "assistant", "content": message}
            if name is None
            else {"role": "assistant", "content": message, "name": name}
        )
        self.limit_messages()
        return self.messages

    def clear_messages(self) -> None:
        self.messages.clear()
        self.tool_calls.clear()
        self.tool_calls_result.clear()

    def add_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for msg in messages:
            if msg.get("role") is None:
                raise ValueError("消息缺少 role 字段")
            if msg.get("content") is None:
                raise ValueError("消息缺少 content 字段")

        self.messages.extend(messages)
        self.limit_messages()
        return self.messages

    def limit_messages(self) -> None:
        """
        限制消息长度在 max_length 内，
        保留最新的消息，删除最老的消息。
        - index 0 通常是 system，不主动删除
        - tool_calls 消息和紧跟的 tool 结果视为一个整体删除
        """
        # 确保所有消息都有 content 字段，避免后面计算长度时报错
        for msg in self.messages:
            if msg.get("content") is None:
                msg["content"] = ""

        total_length = sum(len(msg.get("content", "")) for msg in self.messages)

        i = 1  # 从 1 开始，尽量保留 system 消息
        while total_length > self.max_length and len(self.messages) > 1:
            if i >= len(self.messages):
                break

            msg = self.messages[i]

            # 如果是带 tool_calls 的 assistant 消息，把它和后面的 tool 消息一起删掉
            if msg.get("tool_calls") is not None:
                # 先减去当前消息的 content（通常为空）
                total_length -= len(msg.get("content", ""))

                # 如果后面紧跟着 tool 消息，把它也删掉，并减长度
                if i + 1 < len(self.messages):
                    next_msg = self.messages[i + 1]
                    total_length -= len(next_msg.get("content", ""))
                    self.messages.pop(i + 1)

                # 再删掉当前 tool_calls 消息
                self.messages.pop(i)
                # 不递增 i，继续看当前位置的新消息
                continue

            # 普通消息，直接删掉一条
            total_length -= len(msg.get("content", ""))
            self.messages.pop(i)

        # 循环结束后，如果还是超长，且只有一条 system，可以选择截断 system 的 content
        if self.messages and total_length > self.max_length:
            sys_msg = self.messages[0]
            content = sys_msg.get("content", "")
            if len(content) > self.max_length:
                sys_msg["content"] = content[: self.max_length - 3] + "..."


class MultimodalContextManager(ContextManager):
    """
    多模态上下文管理器，继承自基础上下文管理器
    目前与基础上下文管理器功能相同，但可以根据需要扩展多
    """

    max_length: int
    max_tool_result_length: int
    tool_calls_result: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]
    messages: list[dict[str, Any]]

    def __init__(
        self, tools, max_length: int = 100000, max_tool_result_length: int = 6000
    ) -> None:
        self.max_length = max_length
        self.tools = tools
        self.max_tool_result_length = max_tool_result_length
        self.tool_calls = []  # 初始化 tool_calls
        self.tool_calls_result = []  # 初始化 tool_calls_result
        self.messages = []  # 初始化 messages，确保每个实例都有独立的列表

    def set_messages(self, messages: list[dict[str, Any]]) -> None:
        self.messages = messages

    def get_messages(self) -> list[dict[str, Any]]:
        """返回消息列表"""
        return self.messages

    def get_system_message(self) -> str:
        """返回系统消息（没有则返回空字符串）"""
        if not self.messages:
            return ""
        first = self.messages[0]
        if first.get("role") == "system":
            return first.get("content", "") or ""
        return ""

    def set_system_message(self, message: str) -> None:
        if not self.messages:  # 如果没有系统消息，则创建一个
            self.messages.append({"role": "system", "content": message})
        else:
            # 如果第一条不是 system，也强制替换为 system
            self.messages[0] = {"role": "system", "content": message}

    def add_user_message(
        self,
        instruction: str,
        image: str | list[str],
        audio: str | list[str],
        url: str | list[str],
    ) -> list[dict[str, Any]]:
        user_content = build_multimodal_message(
            input_text=instruction,
            input_image=image,
            input_audio=audio,
            input_url=url,
            role="user",
        )
        if user_content is None:
            return self.messages
        self.messages.append(user_content)
        return self.messages

    def add_tool_calls(self, tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # 给每个 tool_call 补充 tool_call_id

        for tool_call in tool_calls:
            if "tool_call_id" not in tool_call and "id" in tool_call:

                tool_call["tool_call_id"] = tool_call["id"]

        self.tool_calls.extend(tool_calls)

        # assistant 消息中带 tool_calls（content 通常为空）
        self.messages.append(
            {
                "role": "assistant",
                "tool_calls": tool_calls,
                "content": "",
            }
        )
        return tool_calls

    def add_tool_calls_result(self, tool_calls_result: list[dict[str, Any]]) -> None:
        """
        批量追加工具结果。
        要求传进来的每个元素至少包含:
        - "tool_call": 对应的 tool_call（可选）
        - "tool_name": 工具名称（可选）
        - "result": 工具执行结果字符串
        """
        for item in tool_calls_result:
            # 确保有 result 字段
            images = []
            audios = []
            urls = []
            item["result"] = item.get("content", "") or ""
            item["tool_name"] = item.get("tool_name", None)
            self.tool_calls_result.append(item)

            # 同时追加到 messages 中（作为 tool 消息）
            content = str(item.get("result", ""))
            if len(content) > self.max_tool_result_length:
                content = content[: self.max_tool_result_length - 3] + "..."
            self.messages.append(
                {
                    "role": "tool",
                    "content": content,
                    # 如果有 tool_call_id 就带上，方便对齐
                    "tool_call_id": item.get("tool_call_id"),
                }
            )
            self._add_multimodal_message(item, images, audios, urls)

    def _add_multimodal_message(self, item, images, audios, urls):
        if self.tools.get_multimodal_type(item["tool_name"]) == "image":
            if isinstance(item["result"], str):
                images.append(item["result"])
            elif isinstance(item["result"], list):
                images.extend(item["result"])
        if self.tools.get_multimodal_type(item["tool_name"]) == "audio":
            if isinstance(item["result"], str):
                audios.append(item["result"])
            elif isinstance(item["result"], list):
                audios.extend(item["result"])
        if self.tools.get_multimodal_type(item["tool_name"]) == "url":
            if isinstance(item["result"], str):
                urls.append(item["result"])
            elif isinstance(item["result"], list):
                urls.extend(item["result"])
        self.add_user_message(
            instruction=f"工具{item['tool_name']}的结果",
            image=images,
            audio=audios,
            url=urls,
        )

    def add_tool_call_result(
        self, tool_result: str | None, tool_call_id: str, tool_call: dict[str, Any]
    ) -> None:
        if tool_result is None:
            tool_result = ""

        record = {
            "tool_call": tool_call,
            "tool_name": tool_call.get("function", {}).get("name"),
            "result": tool_result,
            "tool_call_id": tool_call_id,
        }
        self.tool_calls_result.append(record)

        # 截断过长的结果再写入 messages
        content = tool_result
        if len(content) > self.max_tool_result_length:
            content = content[: self.max_tool_result_length - 3] + "..."
        self.messages.append(
            {
                "role": "tool",
                "content": content,
                "tool_call_id": tool_call_id,
            }
        )

    def get_tool_calls(self) -> list[dict[str, Any]]:
        return self.tool_calls

    def get_tools_result(self) -> list[dict[str, Any]]:
        """
        返回“完整的工具结果列表”，
        每个元素是一个 dict，至少包含: tool_call, tool_name, result, tool_call_id。
        """
        return self.tool_calls_result

    def get_tool_result_contents(self) -> list[str]:
        """
        只返回工具结果的纯文本列表: [result1, result2, ...]
        """
        return [str(item.get("result", "")) for item in self.tool_calls_result]

    def add_assistant_message(self, message: str) -> list[dict[str, Any]]:
        self.messages.append({"role": "assistant", "content": message})

        return self.messages

    def clear_messages(self) -> None:
        self.messages.clear()
        self.tool_calls.clear()
        self.tool_calls_result.clear()

    def add_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for msg in messages:
            if msg.get("role") is None:
                raise ValueError("消息缺少 role 字段")
            if msg.get("content") is None:
                raise ValueError("消息缺少 content 字段")

        self.messages.extend(messages)

        return self.messages
