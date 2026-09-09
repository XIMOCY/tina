"""
编写者：王出日
日期：2026，3，13
版本 0.5.3
描述：关键词动作。说出关键词触发无参副作用；不进入 tools schema，不可合并。
对应 Unity Tina Keyword Actions 的轻量 Python 实现。
"""

from __future__ import annotations

import inspect
import re
from collections import OrderedDict
from typing import Callable, List

from ...core import logger
from ...core.error import TinaError


class KeywordActions:
    """
    关键词动作集。API 表面积对齐 Tools：装饰器 + 命令式绑定 + 少数 runtime 方法。
    需要参数时请使用 Tools。
    """

    def __init__(self):
        self._actions: List[dict] = []
        self._buffer: str = ""

    # --- 注册 ---

    def bind(
        self,
        keyword: str,
        match: str = "contains",
        display: bool = True,
        description: str = None,
    ):
        """
        装饰器绑定关键词动作（无参函数）。
        @[你实例化的名称].bind(keyword="[Happy]", match="contains", display=False)
        Args:
            keyword: 触发关键词
            match: "contains" | "exact"，默认 contains；匹配忽略大小写
            display: True 显示关键词，False 从可见输出剥离（仅 filter_visible）；默认 True
            description: 可选；不传则读取函数文档字符串（对齐 Tools）
        """

        def decorator(func):
            self.bind_action(
                keyword=keyword,
                func=func,
                match=match,
                display=display,
                description=description,
            )
            return func

        return decorator

    def bind_action(
        self,
        keyword: str,
        func: Callable,
        match: str = "contains",
        display: bool = True,
        description: str = None,
    ) -> None:
        """
        命令式绑定关键词动作，对称 Tools.register_tool。
        Args:
            keyword: 触发关键词
            func: 无参可调用对象
            match: "contains" | "exact"
            display: True 显示 / False 隐藏（可见过滤）
            description: 可选；不传则读取文档字符串
        """
        if not keyword:
            raise TinaError("KeywordActions 的 keyword 不能为空")
        if match is None:
            match = "contains"
        if not isinstance(match, str):
            raise TinaError('match 只能是 "contains" 或 "exact"')
        match = match.lower()
        if match not in ("contains", "exact"):
            raise TinaError('match 只能是 "contains" 或 "exact"')
        if not isinstance(display, bool):
            raise TinaError("display 必须是 bool：True 显示，False 隐藏")
        self._ensure_no_params(func)

        self._actions.append(
            {
                "keyword": keyword,
                "match": match,
                "display": display,
                "description": self._get_description(func, description),
                "name": getattr(func, "__name__", str(func)),
                "func": func,
            }
        )

    def _get_description(self, func: Callable, description: str | None) -> str:
        """对齐 Tools：优先显式 description，否则取 docstring 中 Args 之前的部分。"""
        if description is not None:
            return description
        doc_content = func.__doc__.strip() if func.__doc__ else ""
        if not doc_content:
            return ""
        description_part = re.sub(
            r"\s*Args:\s*.*?(?=\n\s*\w+:|$)", "", doc_content, flags=re.DOTALL
        )
        return description_part.strip()

    def _ensure_no_params(self, func: Callable) -> None:
        if not callable(func):
            raise TinaError("KeywordActions 绑定对象必须可调用")
        params = inspect.signature(func).parameters
        if len(params) > 0:
            raise TinaError(
                f"KeywordActions 不能绑定带参数的函数 `{getattr(func, '__name__', func)}`，"
                f"需要参数请改用 Tools。"
            )

    # --- 匹配与执行（正文凑齐后触发）---

    def check(self, text: str) -> None:
        """
        对完整 assistant 原文做 Contains/Exact 匹配并执行动作（同步路径）。
        匹配忽略大小写；异步回调在同步路径会被忽略并打 warning。
        """
        if not text or not self._actions:
            return
        for entry in self._actions:
            if not self._matches(entry, text):
                continue
            func = entry["func"]
            logger.info(f'关键词动作触发: "{entry["keyword"]}"')
            if inspect.iscoroutinefunction(func):
                logger.warning(
                    f'KeywordActions - 异步动作 "{entry["keyword"]}"'
                    f"（{getattr(func, '__name__', func)}）在同步调用中被忽略，请使用 apredict"
                )
                continue
            try:
                func()
            except Exception as e:
                logger.error(f'关键词动作 "{entry["keyword"]}" 执行失败: {e}')

    async def acheck(self, text: str) -> None:
        """
        异步路径：同步回调直接调，async def 回调 await。
        仅应在 arun_* / apredict 中使用。
        """
        if not text or not self._actions:
            return
        for entry in self._actions:
            if not self._matches(entry, text):
                continue
            func = entry["func"]
            logger.info(f'关键词动作触发: "{entry["keyword"]}"')
            try:
                if inspect.iscoroutinefunction(func):
                    await func()
                else:
                    func()
            except Exception as e:
                logger.error(f'关键词动作 "{entry["keyword"]}" 执行失败: {e}')

    def _matches(self, entry: dict, text: str) -> bool:
        keyword = entry["keyword"]
        if not keyword or not text:
            return False
        if entry["match"] == "exact":
            return text.strip().casefold() == keyword.strip().casefold()
        return keyword.casefold() in text.casefold()

    # --- Hide 可见过滤（对齐 StripHiddenKeywords / FlushKeywordBuffer）---

    def filter_visible(self, content: str) -> str:
        """
        流式消费方用：剥离 display=False 的关键词（大小写敏感），跨 chunk 前缀缓冲。
        不改写历史原文；空 content 不消费缓冲。
        """
        if not content:
            return ""
        full = self._buffer + content
        self._buffer = ""
        out: List[str] = []
        pos = 0
        n = len(full)
        while pos < n:
            matched = False
            for entry in self._actions:
                if entry["display"] or not entry["keyword"]:
                    continue
                kw = entry["keyword"]
                kw_len = len(kw)
                if pos + kw_len <= n and full[pos : pos + kw_len] == kw:
                    pos += kw_len
                    matched = True
                    break
            if not matched and self._is_prefix_of_hidden(full, pos):
                self._buffer = full[pos:]
                break
            if not matched:
                out.append(full[pos])
                pos += 1
        return "".join(out)

    def _is_prefix_of_hidden(self, text: str, pos: int) -> bool:
        suffix = text[pos:]
        if not suffix:
            return False
        for entry in self._actions:
            if entry["display"] or not entry["keyword"]:
                continue
            if entry["keyword"].startswith(suffix):
                return True
        return False

    def flush_visible(self) -> str:
        """
        回合末吐出仍截留的缓冲（未拼成完整隐藏关键词的残留）。
        """
        if not self._buffer:
            return ""
        result = self._buffer
        self._buffer = ""
        return result

    def reset_buffer(self) -> None:
        """新一轮预测开始时清空 Hide 缓冲。"""
        self._buffer = ""

    # --- Prompt ---

    def _group_by_keyword(self) -> OrderedDict:
        """按 keyword 分组（同一关键词可绑多个函数）。"""
        groups: OrderedDict = OrderedDict()
        for entry in self._actions:
            key = entry["keyword"]
            if key not in groups:
                groups[key] = []
            groups[key].append(entry)
        return groups

    def _format_func_line(self, entry: dict) -> str:
        name = entry["name"]
        desc = entry["description"] or f'执行 {entry["keyword"]} 相关动作'
        return f"{name}: {desc}"

    def build_prompt_block(self) -> str:
        """
        生成关键词动作说明块，供拼进 system prompt。
        统一为：触发说明 + 会调用以下的工具：名称: 描述（单绑也带函数名）。
        """
        if not self._actions:
            return ""
        lines = []
        for keyword, entries in self._group_by_keyword().items():
            match = entries[0]["match"]
            if match == "exact":
                head = f'当你说的话只有"{keyword}"的时候会触发'
            else:
                head = f'当你说的话里面包括了"{keyword}"的时候会触发'
            tools_lines = "\n".join(f"- {self._format_func_line(e)}" for e in entries)
            lines.append(f"{head}。会调用以下的工具：\n{tools_lines}")
        return "\n".join(lines)

    # --- 查询 ---

    @property
    def actions(self) -> List[dict]:
        """只读视图：已绑定条目的浅拷贝列表。"""
        return [dict(a) for a in self._actions]

    def __len__(self) -> int:
        return len(self._actions)

    def __bool__(self) -> bool:
        return bool(self._actions)
