import httpx
import json
import os
from typing import AsyncGenerator, Union, Generator
from ..utils.env_reader import EnvReader
from ..core.error import APIRequestFailed
from ..utils.output_parser import stream_generator_parser
from ..utils.multimodal_formatter import build_multimodal_message
from ..core import logger


from .base_api import BaseAPI


class BaseMultimodalAPI(BaseAPI):
    """
    多模态API类，继承自BaseAPI
    扩展了对多图片（本地/URL）和多音频（本地）的支持
    """

    API_ENV_VAR_NAME = "LLM_API_KEY"
    BASE_URL = ""

    def __init__(
        self,
        model: str = None,
        api_key: str = None,
        base_url: str = None,
        env_path: str = None,
        name: str = "None",
        role: str = "user",
    ):
        super().__init__(
            model=model,
            api_key=api_key,
            base_url=base_url,
            env_path=env_path,
            name=name,
            role=role,
        )

    def _prepare_multimodal_messages(
        self,
        input_text: str = None,
        input_image: Union[str, list[str]] = None,
        input_audio: Union[str, list[str]] = None,
        input_url: Union[str, list[str]] = None,
        image_detail: str = "auto",
        role: str = "user",
        sys_prompt: str = "你的工作非常出色！",
        messages: list = None,
    ) -> list:
        """准备多模态消息列表，支持单/多文本、图片、音频"""
        if messages is None:
            messages = [{"role": "system", "content": sys_prompt}]
        if any(_input is not None for _input in [input_image, input_audio, input_url]):
            user_message = build_multimodal_message(
                input_text, input_image, input_audio, input_url, image_detail, role
            )
            messages.append(user_message)
        return messages

    # ========================== 同步接口 ==========================
    def predict(
        self,
        input_text: str = None,
        input_image: Union[str, list[str]] = None,
        input_audio: Union[str, list[str]] = None,
        input_url: Union[str, list[str]] = None,
        image_detail: str = "auto",
        stream: bool = False,
        role: str = "user",
        sys_prompt: str = "你的工作非常出色！",
        messages: list = None,
        temperature: float = 1.0,
        top_p: float = 0.9,
        top_k: int = None,
        min_p: float = None,
        max_tokens: int = None,
        presence_penalty: float = None,
        frequency_penalty: float = None,
        format: str = "text",
        json_format: str = "{}",
        tools: list = None,
        timeout: int = 180,
        **kwargs,
    ):
        """
        多模态预测接口，支持文本、图片、音频和URL输入

        Args:
            input_text (str, optional): 用户输入文本. 默认为 None.
            input_image (Union[str, list[str]], optional): 本地图片路径或图片路径列表. 默认为 None.
            input_audio (Union[str, list[str]], optional): 本地音频路径或音频路径列表. 默认为 None.
            input_url (Union[str, list[str]], optional): 图片URL或URL列表. 默认为 None.
            stream (bool, optional): 是否启用流式响应. 默认 False.
            role (str, optional): 用户角色. 默认 "user".
            sys_prompt (str, optional): 系统提示词. 默认 '你的工作非常出色！'.
            messages (list, optional): 历史对话消息列表. 默认为 None.
            temperature (float, optional): 生成文本的随机性参数 (0.0-1.0). 默认 1.0.
            top_p (float, optional): 核采样参数 (0.0-1.0). 默认 0.9.
            top_k (int, optional): Top-K采样参数，限制候选词汇数量.
                注意：不是所有模型都支持，不支持时会自动忽略. 默认 None.
            min_p (float, optional): Min-P采样参数，设置最小概率阈值.
                注意：较新的采样方法，老模型可能不支持. 默认 None.
            max_tokens (int, optional): 最大生成token数量. 默认 None.
            presence_penalty (float, optional): 存在惩罚参数 (-2.0到2.0). 默认 None.
            frequency_penalty (float, optional): 频率惩罚参数 (-2.0到2.0). 默认 None.
            format (str, optional): 返回格式类型，"text"或"json". 默认 "text".
            json_format (str, optional): JSON格式模板. 默认空字符串.
            tools (list, optional): 工具调用列表. 默认 None.
            timeout (int, optional): 请求超时时间(秒). 默认 180.

        Returns:
            Union[dict, Generator[dict, None, None]]:
            - 非流式模式返回字典格式：
              {"role": "assistant", "content": "...", "tool_calls": [...]}
            - 流式模式返回生成器，逐块返回响应内容和/或工具调用信息
        """
        if stream:
            return self.predict_stream(
                input_text=input_text,
                input_image=input_image,
                input_audio=input_audio,
                input_url=input_url,
                image_detail=image_detail,
                role=role,
                sys_prompt=sys_prompt,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                min_p=min_p,
                max_tokens=max_tokens,
                presence_penalty=presence_penalty,
                frequency_penalty=frequency_penalty,
                format=format,
                json_format=json_format,
                tools=tools,
                timeout=timeout,
                **kwargs,
            )
        else:
            return self.predict_no_stream(
                input_text=input_text,
                input_image=input_image,
                input_audio=input_audio,
                input_url=input_url,
                image_detail=image_detail,
                role=role,
                sys_prompt=sys_prompt,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                min_p=min_p,
                max_tokens=max_tokens,
                presence_penalty=presence_penalty,
                frequency_penalty=frequency_penalty,
                format=format,
                json_format=json_format,
                tools=tools,
                timeout=timeout,
                **kwargs,
            )

    def predict_no_stream(
        self,
        input_text: str = None,
        input_image: Union[str, list[str]] = None,
        input_audio: Union[str, list[str]] = None,
        input_url: Union[str, list[str]] = None,
        image_detail: str = "auto",
        role: str = "user",
        sys_prompt: str = "你的工作非常出色！",
        messages: list = None,
        temperature: float = 1.0,
        top_p: float = 0.9,
        top_k: int = None,
        min_p: float = None,
        max_tokens: int = None,
        presence_penalty: float = None,
        frequency_penalty: float = None,
        format: str = "text",
        json_format: str = "{}",
        tools: list = None,
        timeout: int = 180,
        **kwargs,
    ) -> dict:
        """
        同步非流式多模态API调用，直接返回完整响应

        Args:
            input_text (str, optional): 用户输入文本. 默认为 None.
            input_image (Union[str, list[str]], optional): 本地图片路径或图片路径列表. 默认为 None.
            input_audio (Union[str, list[str]], optional): 本地音频路径或音频路径列表. 默认为 None.
            input_url (Union[str, list[str]], optional): 图片URL或URL列表. 默认为 None.
            role (str, optional): 用户角色. 默认 "user".
            sys_prompt (str, optional): 系统提示词. 默认 '你的工作非常出色！'.
            messages (list, optional): 历史对话消息列表. 默认为 None.
            temperature (float, optional): 生成文本的随机性参数 (0.0-1.0). 默认 1.0.
            top_p (float, optional): 核采样参数 (0.0-1.0). 默认 0.9.
            top_k (int, optional): Top-K采样参数，限制候选词汇数量.
                注意：不是所有模型都支持，不支持时会自动忽略. 默认 None.
            min_p (float, optional): Min-P采样参数，设置最小概率阈值.
                注意：较新的采样方法，老模型可能不支持. 默认 None.
            max_tokens (int, optional): 最大生成token数量. 默认 None.
            presence_penalty (float, optional): 存在惩罚参数 (-2.0到2.0). 默认 None.
            frequency_penalty (float, optional): 频率惩罚参数 (-2.0到2.0). 默认 None.
            format (str, optional): 返回格式类型，"text"或"json". 默认 "text".
            json_format (str, optional): JSON格式模板. 默认空字符串.
            tools (list, optional): 工具调用列表. 默认 None.
            timeout (int, optional): 请求超时时间(秒). 默认 180.

        Returns:
            dict: {"role": "assistant", "content": "...", "tool_calls": [...]}

        Raises:
            APIRequestFailed: 当API调用失败时抛出异常
        """
        prepared_messages = self._prepare_multimodal_messages(
            input_text,
            input_image,
            input_audio,
            input_url,
            image_detail,
            role,
            sys_prompt,
            messages,
        )
        payload = self._prepare_payload(
            messages=prepared_messages,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            min_p=min_p,
            max_tokens=max_tokens,
            presence_penalty=presence_penalty,
            frequency_penalty=frequency_penalty,
            stream=False,
            format=format,
            json_format=json_format,
            tools=tools,
            **kwargs,
        )

        response = httpx.post(
            self.base_url,
            json=payload,
            headers=self._prepare_headers(),
            timeout=timeout,
        )
        if response.status_code != 200:
            raise APIRequestFailed(self.base_url, response.status_code, response.text)

        res_json = response.json()
        self.tokens += res_json.get("usage", {}).get("total_tokens", 0)

        msg = res_json["choices"][0]["message"]
        result = {"role": "assistant", "content": msg.get("content", "")}
        if "tool_calls" in msg:
            result["tool_calls"] = msg["tool_calls"]
        return result

    def predict_stream(
        self,
        input_text: str = None,
        input_image: Union[str, list[str]] = None,
        input_audio: Union[str, list[str]] = None,
        input_url: Union[str, list[str]] = None,
        image_detail: str = "auto",
        role: str = "user",
        sys_prompt: str = "你的工作非常出色！",
        messages: list = None,
        temperature: float = 1.0,
        top_p: float = 0.9,
        top_k: int = None,
        min_p: float = None,
        max_tokens: int = None,
        presence_penalty: float = None,
        frequency_penalty: float = None,
        format: str = "text",
        json_format: str = "{}",
        tools: list = None,
        timeout: int = 180,
        **kwargs,
    ) -> Generator[dict, None, None]:
        """
        同步流式多模态API调用，返回生成器逐块返回响应

        Args:
            input_text (str, optional): 用户输入文本. 默认为 None.
            input_image (Union[str, list[str]], optional): 本地图片路径或图片路径列表. 默认为 None.
            input_audio (Union[str, list[str]], optional): 本地音频路径或音频路径列表. 默认为 None.
            input_url (Union[str, list[str]], optional): 图片URL或URL列表. 默认为 None.
            role (str, optional): 用户角色. 默认 "user".
            sys_prompt (str, optional): 系统提示词. 默认 '你的工作非常出色！'.
            messages (list, optional): 历史对话消息列表. 默认为 None.
            temperature (float, optional): 生成文本的随机性参数 (0.0-1.0). 默认 1.0.
            top_p (float, optional): 核采样参数 (0.0-1.0). 默认 0.9.
            top_k (int, optional): Top-K采样参数，限制候选词汇数量.
                注意：不是所有模型都支持，不支持时会自动忽略. 默认 None.
            min_p (float, optional): Min-P采样参数，设置最小概率阈值.
                注意：较新的采样方法，老模型可能不支持. 默认 None.
            max_tokens (int, optional): 最大生成token数量. 默认 None.
            presence_penalty (float, optional): 存在惩罚参数 (-2.0到2.0). 默认 None.
            frequency_penalty (float, optional): 频率惩罚参数 (-2.0到2.0). 默认 None.
            format (str, optional): 返回格式类型，"text"或"json". 默认 "text".
            json_format (str, optional): JSON格式模板. 默认空字符串.
            tools (list, optional): 工具调用列表. 默认 None.
            timeout (int, optional): 请求超时时间(秒). 默认 180.

        Yields:
            dict: 逐块返回响应内容和/或工具调用信息

        Raises:
            APIRequestFailed: 当API调用失败时抛出异常
        """
        prepared_messages = self._prepare_multimodal_messages(
            input_text,
            input_image,
            input_audio,
            input_url,
            image_detail,
            role,
            sys_prompt,
            messages,
        )
        payload = self._prepare_payload(
            messages=prepared_messages,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            min_p=min_p,
            max_tokens=max_tokens,
            presence_penalty=presence_penalty,
            frequency_penalty=frequency_penalty,
            stream=True,
            format=format,
            json_format=json_format,
            tools=tools,
            **kwargs,
        )
        return stream_generator_parser(
            self.base_url, payload, self._prepare_headers(), timeout
        )

    # ========================== 异步接口 ==========================
    async def apredict(
        self,
        input_text: str = None,
        input_image: Union[str, list[str]] = None,
        input_audio: Union[str, list[str]] = None,
        input_url: Union[str, list[str]] = None,
        image_detail: str = "auto",
        stream: bool = False,
        role: str = "user",
        sys_prompt: str = "你的工作非常出色！",
        messages: list = None,
        temperature: float = 1.0,
        top_p: float = 0.9,
        top_k: int = None,
        min_p: float = None,
        max_tokens: int = None,
        presence_penalty: float = None,
        frequency_penalty: float = None,
        format: str = "text",
        json_format: str = "{}",
        tools: list = None,
        timeout: int = 180,
        **kwargs,
    ):
        """
        异步多模态预测接口，支持文本、图片、音频和URL输入

        Args:
            input_text (str, optional): 用户输入文本. 默认为 None.
            input_image (Union[str, list[str]], optional): 本地图片路径或图片路径列表. 默认为 None.
            input_audio (Union[str, list[str]], optional): 本地音频路径或音频路径列表. 默认为 None.
            input_url (Union[str, list[str]], optional): 图片URL或URL列表. 默认为 None.
            stream (bool, optional): 是否启用流式响应. 默认 False.
            role (str, optional): 用户角色. 默认 "user".
            sys_prompt (str, optional): 系统提示词. 默认 '你的工作非常出色！'.
            messages (list, optional): 历史对话消息列表. 默认为 None.
            temperature (float, optional): 生成文本的随机性参数 (0.0-1.0). 默认 1.0.
            top_p (float, optional): 核采样参数 (0.0-1.0). 默认 0.9.
            top_k (int, optional): Top-K采样参数，限制候选词汇数量.
                注意：不是所有模型都支持，不支持时会自动忽略. 默认 None.
            min_p (float, optional): Min-P采样参数，设置最小概率阈值.
                注意：较新的采样方法，老模型可能不支持. 默认 None.
            max_tokens (int, optional): 最大生成token数量. 默认 None.
            presence_penalty (float, optional): 存在惩罚参数 (-2.0到2.0). 默认 None.
            frequency_penalty (float, optional): 频率惩罚参数 (-2.0到2.0). 默认 None.
            format (str, optional): 返回格式类型，"text"或"json". 默认 "text".
            json_format (str, optional): JSON格式模板. 默认空字符串.
            tools (list, optional): 工具调用列表. 默认 None.
            timeout (int, optional): 请求超时时间(秒). 默认 180.

        Returns:
            Union[dict, Generator[dict, None, None]]:
            - 非流式模式返回字典格式：
              {"role": "assistant", "content": "...", "tool_calls": [...]}
            - 流式模式返回生成器，逐块返回响应内容和/或工具调用信息
        """
        if stream:
            return await self.apredict_stream(
                input_text=input_text,
                input_image=input_image,
                input_audio=input_audio,
                input_url=input_url,
                image_detail=image_detail,
                role=role,
                sys_prompt=sys_prompt,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                min_p=min_p,
                max_tokens=max_tokens,
                presence_penalty=presence_penalty,
                frequency_penalty=frequency_penalty,
                format=format,
                json_format=json_format,
                tools=tools,
                timeout=timeout,
                **kwargs,
            )
        else:
            return await self.apredict_no_stream(
                input_text=input_text,
                input_image=input_image,
                input_audio=input_audio,
                input_url=input_url,
                image_detail=image_detail,
                role=role,
                sys_prompt=sys_prompt,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                min_p=min_p,
                max_tokens=max_tokens,
                presence_penalty=presence_penalty,
                frequency_penalty=frequency_penalty,
                format=format,
                json_format=json_format,
                tools=tools,
                timeout=timeout,
                **kwargs,
            )

    async def apredict_no_stream(
        self,
        input_text: str = None,
        input_image: Union[str, list[str]] = None,
        input_audio: Union[str, list[str]] = None,
        input_url: Union[str, list[str]] = None,
        image_detail: str = "auto",
        role: str = "user",
        sys_prompt: str = "你的工作非常出色！",
        messages: list = None,
        temperature: float = 1.0,
        top_p: float = 0.9,
        top_k: int = None,
        min_p: float = None,
        max_tokens: int = None,
        presence_penalty: float = None,
        frequency_penalty: float = None,
        format: str = "text",
        json_format: str = "{}",
        tools: list = None,
        timeout: int = 180,
        **kwargs,
    ) -> dict:
        """
        异步非流式多模态API调用，直接返回完整响应

        Args:
            input_text (str, optional): 用户输入文本. 默认为 None.
            input_image (Union[str, list[str]], optional): 本地图片路径或图片路径列表. 默认为 None.
            input_audio (Union[str, list[str]], optional): 本地音频路径或音频路径列表. 默认为 None.
            input_url (Union[str, list[str]], optional): 图片URL或URL列表. 默认为 None.
            role (str, optional): 用户角色. 默认 "user".
            sys_prompt (str, optional): 系统提示词. 默认 '你的工作非常出色！'.
            messages (list, optional): 历史对话消息列表. 默认为 None.
            temperature (float, optional): 生成文本的随机性参数 (0.0-1.0). 默认 1.0.
            top_p (float, optional): 核采样参数 (0.0-1.0). 默认 0.9.
            top_k (int, optional): Top-K采样参数，限制候选词汇数量.
                注意：不是所有模型都支持，不支持时会自动忽略. 默认 None.
            min_p (float, optional): Min-P采样参数，设置最小概率阈值.
                注意：较新的采样方法，老模型可能不支持. 默认 None.
            max_tokens (int, optional): 最大生成token数量. 默认 None.
            presence_penalty (float, optional): 存在惩罚参数 (-2.0到2.0). 默认 None.
            frequency_penalty (float, optional): 频率惩罚参数 (-2.0到2.0). 默认 None.
            format (str, optional): 返回格式类型，"text"或"json". 默认 "text".
            json_format (str, optional): JSON格式模板. 默认空字符串.
            tools (list, optional): 工具调用列表. 默认 None.
            timeout (int, optional): 请求超时时间(秒). 默认 180.

        Returns:
            dict: {"role": "assistant", "content": "...", "tool_calls": [...]}

        Raises:
            APIRequestFailed: 当API调用失败时抛出异常
        """
        prepared_messages = self._prepare_multimodal_messages(
            input_text,
            input_image,
            input_audio,
            input_url,
            image_detail,
            role,
            sys_prompt,
            messages,
        )
        payload = self._prepare_payload(
            messages=prepared_messages,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            min_p=min_p,
            max_tokens=max_tokens,
            presence_penalty=presence_penalty,
            frequency_penalty=frequency_penalty,
            stream=False,
            format=format,
            json_format=json_format,
            tools=tools,
            **kwargs,
        )

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.base_url,
                json=payload,
                headers=self._prepare_headers(),
                timeout=timeout,
            )
            if response.status_code != 200:
                raise APIRequestFailed(
                    self.base_url, response.status_code, response.text
                )

            res_json = response.json()
            self.tokens += res_json.get("usage", {}).get("total_tokens", 0)

            msg = res_json["choices"][0]["message"]
            result = {"role": "assistant", "content": msg.get("content", "")}
            if "tool_calls" in msg:
                result["tool_calls"] = msg["tool_calls"]
            return result

    async def apredict_stream(
        self,
        input_text: str = None,
        input_image: Union[str, list[str]] = None,
        input_audio: Union[str, list[str]] = None,
        input_url: Union[str, list[str]] = None,
        image_detail: str = "auto",
        role: str = "user",
        sys_prompt: str = "你的工作非常出色！",
        messages: list = None,
        temperature: float = 1.0,
        top_p: float = 0.9,
        top_k: int = None,
        min_p: float = None,
        max_tokens: int = None,
        presence_penalty: float = None,
        frequency_penalty: float = None,
        format: str = "text",
        json_format: str = "{}",
        tools: list = None,
        timeout: int = 180,
        **kwargs,
    ) -> AsyncGenerator[dict, None]:
        """
        异步流式多模态API调用，返回生成器逐块返回响应

        Args:
            input_text (str, optional): 用户输入文本. 默认为 None.
            input_image (Union[str, list[str]], optional): 本地图片路径或图片路径列表. 默认为 None.
            input_audio (Union[str, list[str]], optional): 本地音频路径或音频路径列表. 默认为 None.
            input_url (Union[str, list[str]], optional): 图片URL或URL列表. 默认为 None.
            role (str, optional): 用户角色. 默认 "user".
            sys_prompt (str, optional): 系统提示词. 默认 '你的工作非常出色！'.
            messages (list, optional): 历史对话消息列表. 默认为 None.
            temperature (float, optional): 生成文本的随机性参数 (0.0-1.0). 默认 1.0.
            top_p (float, optional): 核采样参数 (0.0-1.0). 默认 0.9.
            top_k (int, optional): Top-K采样参数，限制候选词汇数量.
                注意：不是所有模型都支持，不支持时会自动忽略. 默认 None.
            min_p (float, optional): Min-P采样参数，设置最小概率阈值.
                注意：较新的采样方法，老模型可能不支持. 默认 None.
            max_tokens (int, optional): 最大生成token数量. 默认 None.
            presence_penalty (float, optional): 存在惩罚参数 (-2.0到2.0). 默认 None.
            frequency_penalty (float, optional): 频率惩罚参数 (-2.0到2.0). 默认 None.
            format (str, optional): 返回格式类型，"text"或"json". 默认 "text".
            json_format (str, optional): JSON格式模板. 默认空字符串.
            tools (list, optional): 工具调用列表. 默认 None.
            timeout (int, optional): 请求超时时间(秒). 默认 180.

        Yields:
            dict: 逐块返回响应内容和/或工具调用信息

        Raises:
            APIRequestFailed: 当API调用失败时抛出异常
        """
        from ..utils.output_parser import astream_generator_parser

        prepared_messages = self._prepare_multimodal_messages(
            input_text,
            input_image,
            input_audio,
            input_url,
            image_detail,
            role,
            sys_prompt,
            messages,
        )
        payload = self._prepare_payload(
            messages=prepared_messages,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            min_p=min_p,
            max_tokens=max_tokens,
            presence_penalty=presence_penalty,
            frequency_penalty=frequency_penalty,
            stream=True,
            format=format,
            json_format=json_format,
            tools=tools,
            **kwargs,
        )
        return astream_generator_parser(
            self.aclient, self.base_url, payload, self._prepare_headers(), timeout
        )
