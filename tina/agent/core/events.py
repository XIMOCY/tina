from __future__ import annotations

import inspect
from types import MappingProxyType
from typing import Any, Awaitable, Callable, Protocol, Union
from ...core import logger
from ...core.error import NoConfirmationHandler
from copy import deepcopy
from .agent_response import AgentResponse


class AgentEvents:
    def __init__(self):
        """
        事件管理器
        注意：异步的事件处理函数只会在使用了异步方法的时候起作用
        同步的事件处理函数会在异步和同步的方法里面都执行
        如果要在同步的调用中使用异步的事件处理函数，请自己包裹为同步方法
        """

        self.event_handler = {
            # 发生了工具执行之前
            "before_tool_call": [],
            # 发生了工具执行之后
            # 要求监听者接受工具名称和结果
            "after_tool_call": [],
            # 发生了工具调用之前
            "before_tool_calls": [],
            # 发生了工具调用之后
            "after_tool_calls": [],
            # 发生了用户输入之前
            "before_user_instruction": [],
            # 发生了用户输入之后
            # 要求监听者接受用户输入，默认str
            "after_user_instruction": [],
            # 如果工具需要验证的情况，请监听此事件
            "on_tool_confirmation": None,
            # 处理流式输出的每一个chunk
            "on_stream_chunk": [],
        }


    def get_handler(self, event_name: str):
        return self.event_handler[event_name]

    def get_tool_confirmation_handler(self):
        return self.event_handler["on_tool_confirmation"]

    def _validate_event_handler_signature(self, event_name: str, func: callable):
        """
        验证事件处理函数的签名是否符合要求
        """
        sig = inspect.signature(func)
        params = list(sig.parameters.values())

        # 定义各事件的参数要求
        event_requirements = {
            "before_tool_call": {
                "min_params": 2,
                "param_types": [str, dict],  # 简化检查，实际可能需要更详细的类型检查
            },
            "after_tool_call": {"min_params": 3, "param_types": [str, dict, any]},
            "before_tool_calls": {"min_params": 1, "param_types": [list]},
            "after_tool_calls": {"min_params": 1, "param_types": [list]},
            "before_user_instruction": {"min_params": 1, "param_types": [str]},
            "after_user_instruction": {"min_params": 2, "param_types": [str, str]},
            "on_stream_chunk": {"min_params": 1, "param_types": [dict]},
            "on_tool_confirmation": {"min_params": 2, "param_types": [str, dict]},
        }

        if event_name not in event_requirements:
            return  # 未知事件类型，跳过验证

        requirements = event_requirements[event_name]

        # 检查参数数量
        if len(params) < requirements["min_params"]:
            raise ValueError(
                f'{event_name} 事件处理函数至少需要 {requirements["min_params"]} 个参数'
            )

    def add_handler(self, event_name: str, func):
        if event_name not in self.event_handler:  # 检查事件名称是否合法
            logger.error(f"Events - {event_name} 不是一个有效事件名称")
            raise ValueError(f"{event_name} 不是一个有效的事件名称")
        if event_name == "on_tool_confirmation":
            self.event_handler["on_tool_confirmation"] = func
        else:
            self.event_handler[event_name].append(func)

    def on_stream_chunk(self):
        """
        在大模型处理用户输入时，每处理一个chunk，都会调用此函数
        需要事件处理函数接受下面的参数：
        chunk: dict[str,str] or AgentResponse
        """

        def decorator(func):
            self._validate_event_handler_signature("on_stream_chunk", func)
            self.add_handler("on_stream_chunk", func)
            return func

        return decorator

    def add_on_stream_chunk_handler(self, func: callable | list[callable]):
        """
        在大模型处理用户输入时，每处理一个chunk，都会调用此函数
        需要事件处理函数接受下面的参数：
        chunk: dict[str,str] or AgentResponse
        """
        if isinstance(func, list):
            for f in func:
                self._validate_event_handler_signature("on_stream_chunk", f)
                self.add_handler("on_stream_chunk", f)
        else:
            self._validate_event_handler_signature("on_stream_chunk", func)
            self.add_handler("on_stream_chunk", func)

    def before_tool_call(self):
        """
        在执行工具调用之 前
        需要事件处理函数接受下面的参数：
        tool_name: str,tool_arguments: dict,
        """

        def decorator(func):
            self._validate_event_handler_signature("before_tool_call", func)
            self.add_handler("before_tool_call", func)
            return func

        return decorator

    def add_before_tool_call_handler(self, func: callable | list[callable]):
        """
        在执行工具调用之 前
        需要事件处理函数接受下面的参数：
        tool_name: str,tool_arguments: dict,
        """
        if isinstance(func, list):
            for f in func:
                self._validate_event_handler_signature("before_tool_call", f)
                self.add_handler("before_tool_call", f)
        else:
            self._validate_event_handler_signature("before_tool_call", func)
            self.add_handler("before_tool_call", func)

    def after_tool_call(self):
        """
        在执行工具调用之 后
        需要事件处理函数接受下面的参数：
        tool_name: str,tool_arguments: dict,tool_result: any
        """

        def wrapper(func):
            self._validate_event_handler_signature("after_tool_call", func)
            self.add_handler("after_tool_call", func)
            return func

        return wrapper

    def add_after_tool_call_handler(self, func: callable | list[callable]):
        """
        在执行工具调用之 后
        需要事件处理函数接受下面的参数：
        tool_name: str,tool_arguments: dict,tool_result: any
        """
        if isinstance(func, list):
            for f in func:
                self._validate_event_handler_signature("after_tool_call", f)
                self.add_handler("after_tool_call", f)
        else:
            self._validate_event_handler_signature("after_tool_call", func)

            self.add_handler("after_tool_call", func)

    def before_tool_calls(self):
        """
        在工具调用被大模型处理之前
        需要事件处理函数接受下面的参数：
        tool_calls: list[dict[str,str]]
        """

        def decorator(func):
            self._validate_event_handler_signature("before_tool_calls", func)
            self.add_handler("before_tool_calls", func)
            return func

        return decorator

    def add_before_tool_calls_handler(self, func: callable | list[callable]):
        """
        在工具调用被大模型处理之前
        需要事件处理函数接受下面的参数：
        tool_calls: list[dict[str,str]]
        """
        if isinstance(func, list):
            for f in func:
                self._validate_event_handler_signature("before_tool_calls", f)
                self.add_handler("before_tool_calls", f)
        else:
            self._validate_event_handler_signature("before_tool_calls", func)

            self.add_handler("before_tool_calls", func)

    def after_tool_calls(self):
        """
        在工具调用被大模型处理之后
        需要事件处理函数接受下面的参数：
        tool_calls: list[dict[str,str]]
        """

        def decorator(func):
            self._validate_event_handler_signature("after_tool_calls", func)
            self.add_handler("after_tool_calls", func)
            return func

        return decorator

    def add_after_tool_calls_handler(self, func: callable | list[callable]):
        """
        在工具调用被大模型处理之后
        需要事件处理函数接受下面的参数：
        tool_calls: list[dict[str,str]]
        """
        if isinstance(func, list):
            for f in func:
                self._validate_event_handler_signature("after_tool_calls", f)
                self.add_handler("after_tool_calls", f)
        else:
            self._validate_event_handler_signature("after_tool_calls", func)
            self.add_handler("after_tool_calls", func)

    def on_tool_confirmation(self):
        """
        如果一个工具被登记为需要验证猜可以运行，请监听此事件
        需要事件处理函数接受下面的参数：
        tool_name: str tool_arguments: dict
        """

        def decorator(func):
            self._validate_event_handler_signature("on_tool_confirmation", func)
            self.event_handler["on_tool_confirmation"] = func
            return func

        return decorator

    def add_on_tool_confirmation_handler(self, func: callable):
        """
        如果一个工具被登记为需要验证猜可以运行，请监听此事件
        需要事件处理函数接受下面的参数：
        tool_name: str tool_arguments: dict
        """

        self._validate_event_handler_signature("on_tool_confirmation", func)

        self.add_handler("on_tool_confirmation", func)

    def before_user_instruction(self):
        """
        在用户输入被大模型处理之前
        需要事件处理函数接受下面的参数：
        user_message: str
        """

        def decorator(func):
            self._validate_event_handler_signature("before_user_instruction", func)
            self.add_handler("before_user_instruction", func)
            return func

        return decorator

    def add_before_user_instruction_handler(self, func: callable | list[callable]):
        """
        在用户输入被大模型处理之前
        需要事件处理函数接受下面的参数：
        user_message: str
        """
        if isinstance(func, list):
            for f in func:
                self._validate_event_handler_signature("before_user_instruction", f)
                self.add_handler("before_user_instruction", f)
        else:
            self._validate_event_handler_signature("before_user_instruction", func)
            self.add_handler("before_user_instruction", func)

    def after_user_instruction(self):
        """
        在用户输入被大模型处理之后
        需要事件处理函数接受下面的参数：
        user_message: str assistant_message: str
        """

        def decorator(func):
            self._validate_event_handler_signature("after_user_instruction", func)
            self.add_handler("after_user_instruction", func)
            return func

        return decorator

    def add_after_user_instruction_handler(self, func: callable | list[callable]):
        """
        在用户输入被大模型处理之后
        需要事件处理函数接受下面的参数：
        user_message: str assistant_message: str
        """
        if isinstance(func, list):
            for f in func:
                self._validate_event_handler_signature("after_user_instruction", f)
                self.add_handler("after_user_instruction", f)
        else:
            self._validate_event_handler_signature("after_user_instruction", func)
            self.add_handler("after_user_instruction", func)

    def trigger_before_user_instruction(self, user_message: str):
        changed_message = user_message
        for func in self.event_handler["before_user_instruction"]:
            if inspect.iscoroutinefunction(func):
                logger.warning(
                    f"Events - 异步事件before_user_instruction处理器{func.__name__}在同步调用中被忽略"
                )
                continue
            result = func(changed_message)
            logger.debug(
                f"Events - before_user_instrunction处理器{func.__name__}返回结果{result}"
            )
            if result is not None and isinstance(result, str):
                changed_message = result
            else:
                continue

        return changed_message

    async def atrigger_before_user_instruction(self, user_message: str):
        changed_message = user_message
        for func in self.event_handler["before_user_instruction"]:
            if inspect.iscoroutinefunction(func):
                result = await func(changed_message)
            else:
                result = func(changed_message)
            logger.debug(
                f"Events - before_user_instrunction处理器{func.__name__}返回结果{result}"
            )
            if result is not None and isinstance(result, str):
                changed_message = result
            else:
                continue

        return changed_message

    def trigger_after_user_instruction(self, user_message: str, assistant_message: str):
        changed_user_message = user_message
        changed_assistant_message = assistant_message

        for func in self.event_handler["after_user_instruction"]:
            if inspect.iscoroutinefunction(func):
                logger.warning(
                    f"Events - 异步事件after_user_instruction处理器{func.__name__}在同步调用中被忽略"
                )
                continue
            result = func(changed_user_message, changed_assistant_message)
            logger.debug(
                f"Events - after_user_instrunction处理器{func.__name__}返回结果{result}"
            )
            if result is not None and isinstance(result, tuple):
                if len(result) == 2:
                    changed_user_message = result[0]
                    changed_assistant_message = result[1]

        return changed_user_message, changed_assistant_message

    async def atrigger_after_user_instruction(
        self, user_message: str, assistant_message: str
    ):
        changed_user_message = user_message
        changed_assistant_message = assistant_message

        for func in self.event_handler["after_user_instruction"]:
            if inspect.iscoroutinefunction(func):
                result = await func(changed_user_message, changed_assistant_message)
            else:
                result = func(changed_user_message, changed_assistant_message)
            logger.debug(
                f"Events - after_user_instrunction处理器{func.__name__}返回结果{result}"
            )
            if result is not None and isinstance(result, tuple):
                if len(result) == 2:
                    changed_user_message = result[0]
                    changed_assistant_message = result[1]

        return changed_user_message, changed_assistant_message

    def trigger_before_tool_call(self, tool_name: str, tool_arguments: dict):
        changed_tool_name = tool_name
        changed_tool_arguments = deepcopy(tool_arguments)
        for func in self.event_handler["before_tool_call"]:
            if inspect.iscoroutinefunction(func):
                logger.warning(
                    f"Events - 异步事件before_tool_call处理器{func.__name__}在同步调用中被忽略"
                )
                continue
            result = func(changed_tool_name, changed_tool_arguments)
            logger.debug(
                f"Events - before_tool_call处理器{func.__name__}返回结果{result}"
            )
            if result is not None and isinstance(result, tuple):
                if len(result) == 2:
                    changed_tool_name = result[0]
                    changed_tool_arguments = result[1]
            else:
                continue

        return changed_tool_name, changed_tool_arguments

    async def atrigger_before_tool_call(self, tool_name: str, tool_arguments: dict):
        changed_tool_name = tool_name
        changed_tool_arguments = deepcopy(tool_arguments)
        for func in self.event_handler["before_tool_call"]:
            if inspect.iscoroutinefunction(func):
                result = await func(changed_tool_name, changed_tool_arguments)
            else:
                result = func(changed_tool_name, changed_tool_arguments)
            logger.debug(
                f"Events - before_tool_call处理器{func.__name__}返回结果{result}"
            )
            if result is not None and isinstance(result, tuple):
                if len(result) == 2:
                    changed_tool_name = result[0]
                    changed_tool_arguments = result[1]
            else:
                continue

        return changed_tool_name, changed_tool_arguments

    def trigger_after_tool_call(
        self, tool_name: str, tool_arguments: dict, tool_result: any
    ):
        changed_tool_name = tool_name
        changed_tool_arguments = deepcopy(tool_arguments)
        changed_tool_result = deepcopy(tool_result)
        for func in self.event_handler["after_tool_call"]:
            if inspect.iscoroutinefunction(func):
                logger.warning(
                    f"Events - 异步事件after_tool_call处理器{func.__name__}在同步调用中被忽略"
                )
                continue
            result = func(
                changed_tool_name, changed_tool_arguments, changed_tool_result
            )
            logger.debug(
                f"Events - after_tool_call处理器{func.__name__}返回结果{result}"
            )
            if result is not None and isinstance(result, tuple):
                if len(result) == 3:
                    changed_tool_name = result[0]
                    changed_tool_arguments = result[1]
                    changed_tool_result = result[2]
            else:
                continue
        return changed_tool_name, changed_tool_arguments, changed_tool_result

    async def atrigger_after_tool_call(
        self, tool_name: str, tool_arguments: dict, tool_result: any
    ):
        changed_tool_name = tool_name
        changed_tool_arguments = deepcopy(tool_arguments)
        changed_tool_result = deepcopy(tool_result)
        for func in self.event_handler["after_tool_call"]:
            if inspect.iscoroutinefunction(func):
                result = await func(
                    changed_tool_name, changed_tool_arguments, changed_tool_result
                )
            else:
                result = func(
                    changed_tool_name, changed_tool_arguments, changed_tool_result
                )
            logger.debug(
                f"Events - after_tool_call处理器{func.__name__}返回结果{result}"
            )
            if result is not None and isinstance(result, tuple):
                if len(result) == 3:
                    changed_tool_name = result[0]
                    changed_tool_arguments = result[1]
                    changed_tool_result = result[2]
            else:
                continue
        return changed_tool_name, changed_tool_arguments, changed_tool_result

    def trigger_after_tool_calls(self, tool_calls: list[dict]):
        changed_tool_calls = deepcopy(tool_calls)
        for func in self.event_handler["after_tool_calls"]:
            if inspect.iscoroutinefunction(func):
                logger.warning(
                    f"Events - 异步事件after_tool_calls处理器{func.__name__}在同步调用中被忽略"
                )
                continue
            result = func(changed_tool_calls)

    async def atrigger_after_tool_calls(self, tool_calls: list[dict]):
        changed_tool_calls = deepcopy(tool_calls)
        for func in self.event_handler["after_tool_calls"]:
            if inspect.iscoroutinefunction(func):
                await func(changed_tool_calls)
            else:
                func(changed_tool_calls)

    def trigger_before_tool_calls(self, tool_calls: list[dict]):
        changed_tool_calls = deepcopy(tool_calls)
        for func in self.event_handler["before_tool_calls"]:
            if inspect.iscoroutinefunction(func):
                logger.warning(
                    f"Events - 异步事件before_tool_calls处理器{func.__name__}在同步调用中被忽略"
                )
                continue
            func(changed_tool_calls)

    async def atrigger_before_tool_calls(self, tool_calls: list[dict]):
        changed_tool_calls = deepcopy(tool_calls)
        for func in self.event_handler["before_tool_calls"]:
            if inspect.iscoroutinefunction(func):
                await func(changed_tool_calls)
            else:
                func(changed_tool_calls)

    def trigger_on_tool_confirmation(self, tool_name: str, tool_arguments: dict):
        func = self.event_handler["on_tool_confirmation"]
        if func is None:
            logger.error("Events - 没有设置on_tool_confirmation处理器")
            raise NoConfirmationHandler()
        if inspect.iscoroutinefunction(func):
            logger.warning(
                f"Events - 异步事件on_tool_confirmation处理器{func.__name__}在同步调用中被忽略"
            )
            return False

        result = func(tool_name, tool_arguments)

        if isinstance(result, bool):
            return (result, "用户阻止了该工具的运行")
        elif isinstance(result, tuple):
            return (result[0], result[1])
        return (False, "用户阻止了该工具的运行")

    async def atrigger_on_tool_confirmation(self, tool_name: str, tool_arguments: dict):
        func = self.event_handler["on_tool_confirmation"]
        if func is None:
            logger.error("Events - 没有设置on_tool_confirmation处理器")
            raise NoConfirmationHandler()
        if inspect.iscoroutinefunction(func):
            result = await func(tool_name, tool_arguments)
        else:
            result = func(tool_name, tool_arguments)

        if isinstance(result, bool):
            return (result, "用户阻止了该工具的运行")
        elif isinstance(result, tuple):
            return (result[0], result[1])
        return (False, "用户阻止了该工具的运行")

    def trigger_on_stream_chunk(self, chunk: dict):
        changed_chunk = MappingProxyType(chunk)
        changed_chunk = AgentResponse(**chunk)
        for func in self.event_handler["on_stream_chunk"]:
            if inspect.iscoroutinefunction(func):
                logger.warning(
                    f"Events - 异步事件on_stream_chunk处理器{func.__name__}在同步调用中被忽略"
                )
                continue
            result = func(changed_chunk)
            logger.debug(
                f"Events - on_stream_chunk处理器{func.__name__}返回结果{result}"
            )

    async def atrigger_on_stream_chunk(self, chunk: dict):
        changed_chunk = MappingProxyType(chunk)
        changed_chunk = AgentResponse(**changed_chunk)
        for func in self.event_handler["on_stream_chunk"]:
            if inspect.iscoroutinefunction(func):
                result = await func(changed_chunk)
            else:
                result = func(changed_chunk)
            logger.debug(
                f"Events - on_stream_chunk处理器{func.__name__}返回结果{result}"
            )
