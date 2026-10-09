"""tina 编码工具包

面向「写代码」的工具集（命名空间 ``code``），像普通工具包一样按需搭配：

    from tina import Agent
    from tina.utils.coding_tools import CodingTools

    agent = Agent(llm=llm, tools=CodingTools(root=".").get_tools())

暴露给模型的工具名带 ``code_`` 前缀：``code_read`` / ``code_glob`` / ``code_grep`` /
``code_write`` / ``code_edit`` / ``code_patch`` / ``code_bash``。

设计重点在**可靠的局部编辑**（``code_edit``，精确文本匹配 + 唯一性校验 + 原子写；
``code_patch``，unified diff 批量应用 + 上下文校验 + 原子写）、搜索增强与命令输出截断。
"""

import ast
import difflib
import fnmatch
import os
import platform
import re
import subprocess
import tempfile
import threading

from tina import Tools

# 每个文件的写锁：tina 会并发执行同一条消息里的多个工具调用，
# 同一文件的「读-改-写」必须串行，否则后写覆盖先写、甚至写坏。
_FILE_LOCKS: dict[str, threading.Lock] = {}
_FILE_LOCKS_GUARD = threading.Lock()


def _file_lock(path: str) -> threading.Lock:
    """取得某个绝对路径对应的进程级互斥锁（跨实例共享，按路径归一化）"""
    key = os.path.normcase(os.path.abspath(path))
    with _FILE_LOCKS_GUARD:
        lock = _FILE_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _FILE_LOCKS[key] = lock
        return lock

# 遍历/搜索时默认忽略的目录
_IGNORE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "node_modules",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".idea",
    ".vscode",
    ".tox",
    ".eggs",
    "dist",
    "build",
}

# 单个文件参与文本搜索的最大体积（字节）
_MAX_SEARCH_FILE_SIZE = 2 * 1024 * 1024


def _match_glob(rel_path: str, pattern: str) -> bool:
    """匹配相对路径。支持 ``**/*.py`` / ``*.py`` / ``src/*.py`` 等常见写法。"""
    rel = rel_path.replace(os.sep, "/")
    base = os.path.basename(rel)
    if pattern.startswith("**/"):
        tail = pattern[3:]
        return fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(base, tail)
    if "/" in pattern:
        return fnmatch.fnmatch(rel, pattern)
    return fnmatch.fnmatch(base, pattern)


def _unified_diff(old: str, new: str, path: str, max_chars: int) -> str:
    diff = "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            n=1,
        )
    )
    if not diff:
        return "（无内容变化）"
    if len(diff) > max_chars:
        diff = diff[:max_chars] + f"\n...（diff 已截断，共 {len(diff)} 字符）"
    return diff


# unified diff 的 hunk 头：@@ -旧起点[,旧行数] +新起点[,新行数] @@
_HUNK_HEADER_RE = re.compile(r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@")


def _parse_unified_diff(patch: str) -> list[dict]:
    """把 unified diff 文本解析成 hunk 列表

    每个 hunk 为 ``{"old_start", "old_count", "new_start", "new_count", "lines"}``，
    其中 ``lines`` 是 ``(tag, text)`` 列表，tag ∈ ``" "``（上下文）/ ``"-"``（删除）/
    ``"+"``（新增）。``---``/``+++``/``diff``/``index`` 等头部行会被忽略。

    行数按 hunk 头声明值解析（而非按行前缀猜测），因此删除内容本身以 ``--`` 开头等
    边界情况也不会被误判为文件头。解析出的实际行数与声明不符时抛 ``ValueError``。
    """
    raw = patch.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    hunks: list[dict] = []
    i, n = 0, len(raw)
    while i < n:
        m = _HUNK_HEADER_RE.match(raw[i])
        if not m:
            i += 1
            continue
        old_start = int(m.group(1))
        old_count = int(m.group(2)) if m.group(2) is not None else 1
        new_start = int(m.group(3))
        new_count = int(m.group(4)) if m.group(4) is not None else 1
        body: list[tuple[str, str]] = []
        old_seen = new_seen = 0
        i += 1
        while i < n and (old_seen < old_count or new_seen < new_count):
            line = raw[i]
            tag = line[:1]
            if tag == " ":
                body.append((" ", line[1:]))
                old_seen += 1
                new_seen += 1
            elif tag == "-":
                body.append(("-", line[1:]))
                old_seen += 1
            elif tag == "+":
                body.append(("+", line[1:]))
                new_seen += 1
            elif line == "":
                # 有些工具会去掉行首空格，空行按「空上下文行」处理
                body.append((" ", ""))
                old_seen += 1
                new_seen += 1
            elif tag == "\\":
                # \ No newline at end of file —— 只影响末尾换行，这里跳过
                pass
            else:
                break
            i += 1
        if old_seen != old_count or new_seen != new_count:
            raise ValueError(
                f"hunk @@ -{old_start},{old_count} +{new_start},{new_count} @@ "
                f"声明 {old_count} 旧行 / {new_count} 新行，"
                f"实际解析到 {old_seen} / {new_seen} 行（补丁可能被截断或格式错误）"
            )
        hunks.append(
            {
                "old_start": old_start,
                "old_count": old_count,
                "new_start": new_start,
                "new_count": new_count,
                "lines": body,
            }
        )
    return hunks


def _locate_block(lines: list[str], block: list[str], expected: int) -> int | None:
    """在 ``lines`` 中定位 ``block``（精确逐行匹配），返回起始下标

    找到多处时优先返回最靠近 ``expected`` 的一处（容忍补丁行号有偏差）。
    ``block`` 为空（纯插入）时返回夹紧后的 ``expected``；找不到返回 ``None``。
    """
    if not block:
        return max(0, min(expected, len(lines)))
    span = len(block)
    best: int | None = None
    for start in range(0, len(lines) - span + 1):
        if lines[start : start + span] == block:
            if best is None or abs(start - expected) < abs(best - expected):
                best = start
    return best


def _apply_hunks(
    lines: list[str], hunks: list[dict]
) -> tuple[list[str] | None, int | None]:
    """按顺序应用所有 hunk

    返回 ``(新行列表, 失败的 hunk 下标)``：全部成功时第二项为 ``None``；
    任一 hunk 的上下文对不上则返回 ``(None, 下标)``，不做任何改动。
    """
    result = list(lines)
    offset = 0  # 已应用 hunk 造成的行数位移，用于推算后续 hunk 的期望位置
    for idx, hunk in enumerate(hunks):
        old_block = [t for tag, t in hunk["lines"] if tag in (" ", "-")]
        new_block = [t for tag, t in hunk["lines"] if tag in (" ", "+")]
        # 旧侧首行的 0 基下标是 old_start-1；纯插入（旧侧为空）时 old_start 表示
        # 插入点前的旧行数，故下标直接取 old_start。
        if old_block:
            expected = hunk["old_start"] - 1 + offset
        else:
            expected = hunk["old_start"] + offset
        start = _locate_block(result, old_block, expected)
        if start is None:
            return None, idx
        result[start : start + len(old_block)] = new_block
        offset += len(new_block) - len(old_block)
    return result, None


class CodingTools:
    """编码工具包

    按需挂到任意 Agent。所有相对路径都以 ``root`` 为基准解析。

    Args:
        root: 项目根目录（相对路径会转成绝对路径）
        sandbox: 可选的命令执行后端（实现 ``execute(command, timeout)``）；
            不传则在本机执行 ``code_bash``（支持 cwd）
        read_only: 只暴露只读工具（read/glob/grep），不给 write/edit/patch/bash
        max_results: glob/grep 默认返回上限
        max_read_lines: code_read 默认单次返回行数上限
        max_output_chars: code_bash / diff 的输出截断阈值
    """

    def __init__(
        self,
        root: str = ".",
        sandbox=None,
        read_only: bool = False,
        max_results: int = 200,
        max_read_lines: int = 400,
        max_output_chars: int = 8000,
    ) -> None:
        self.root = os.path.abspath(root)
        self.sandbox = sandbox
        self.read_only = read_only
        self.max_results = max_results
        self.max_read_lines = max_read_lines
        self.max_output_chars = max_output_chars
        self.max_diff_chars = max(2000, max_output_chars // 2)

        self.tools = Tools(name="code")
        self.tools.register_tool(tool=self.read)
        self.tools.register_tool(tool=self.glob)
        self.tools.register_tool(tool=self.grep)
        if not read_only:
            self.tools.register_tool(tool=self.write, require_confirmation=True)
            self.tools.register_tool(tool=self.edit, require_confirmation=True)
            self.tools.register_tool(tool=self.patch, require_confirmation=True)
            self.tools.register_tool(tool=self.bash, require_confirmation=True,timeout=-1)

    def get_tools(self) -> Tools:
        """把工具包公开出去"""
        return self.tools

    # ------------------------------------------------------------------ 辅助

    def _resolve(self, path: str) -> str:
        if not path:
            path = "."
        if os.path.isabs(path):
            return os.path.normpath(path)
        return os.path.normpath(os.path.join(self.root, path))

    def _truncate(self, text: str) -> str:
        limit = self.max_output_chars
        if len(text) <= limit:
            return text
        head = text[: limit * 3 // 4]
        tail = text[-(limit // 4):]
        return f"{head}\n\n...（省略 {len(text) - limit} 字符）...\n\n{tail}"

    def _nearest_hint(self, content: str, old: str) -> str:
        """code_edit 未命中时，给出文件中最接近的片段"""
        old_lines = old.splitlines()
        if not old_lines:
            return ""
        content_lines = content.splitlines()
        first = old_lines[0].strip()
        if first:
            idxs = [i for i, line in enumerate(content_lines) if line.strip() == first]
        else:
            idxs = []
        index = None
        if idxs:
            index = idxs[0]
        else:
            stripped = [line.strip() for line in content_lines]
            close = difflib.get_close_matches(first, stripped, n=1, cutoff=0.6) if first else []
            if close:
                index = stripped.index(close[0])
        if index is None:
            return "（未能找到相近片段，请用 code_read 确认文件内容）"
        start = max(0, index - 2)
        end = min(len(content_lines), index + len(old_lines) + 2)
        snippet = "\n".join(
            f"{i + 1}| {content_lines[i]}" for i in range(start, end)
        )
        return f"文件中最接近的位置（第 {index + 1} 行附近）：\n{snippet}"

    @staticmethod
    def _atomic_write(abs_path: str, content: str) -> None:
        """原子写：写同目录的**唯一**临时文件再 os.replace

        唯一名字很关键：并发写同一文件时，固定临时名会被多个线程交错写入而损坏。
        """
        directory = os.path.dirname(abs_path) or "."
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tina_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, abs_path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    # ------------------------------------------------------------------ 读取

    def read(self, path: str, offset: int = 1, limit: int = None) -> str:
        """
        按行读取文件内容（带行号），支持分页
        Args:
            path (str): 文件路径（相对项目根或绝对路径）
            offset (int): 起始行，从 1 开始
            limit (int): 最多返回的行数，默认取工具配置
        Returns:
            str: 行号化内容；含总行数与截断提示
        """
        abs_path = self._resolve(path)
        if not os.path.isfile(abs_path):
            return f"错误：文件不存在：{path}"
        offset = max(1, int(offset))
        limit = self.max_read_lines if limit is None else max(1, int(limit))
        try:
            with open(abs_path, "r", encoding="utf-8", newline="") as f:
                lines = f.read().splitlines()
        except UnicodeDecodeError:
            return f"错误：二进制或非 UTF-8 文件：{path}"
        except OSError as e:
            return f"错误：读取失败：{e}"

        total = len(lines)
        if total == 0:
            return f"{path}（空文件）"
        start = offset - 1
        end = min(total, start + limit)
        chunk = lines[start:end]
        if not chunk:
            return f"错误：offset={offset} 超出文件范围（共 {total} 行）"

        width = len(str(end))
        body = "\n".join(f"{i + offset:>{width}}| {t}" for i, t in enumerate(chunk))
        header = f"{path}（共 {total} 行，显示 {offset}-{end}）"
        if end < total:
            body += f"\n...（还有 {total - end} 行，用 offset={end + 1} 继续）"
        return header + "\n" + body

    def glob(self, pattern: str, root: str = ".") -> str:
        """
        按 glob 模式查找文件（如 **/*.py），自动忽略常见无关目录
        Args:
            pattern (str): glob 模式，例如 **/*.py、*.md、src/*.ts
            root (str): 搜索起始目录（相对项目根或绝对路径）
        Returns:
            str: 匹配的文件路径列表（相对项目根）
        """
        base = self._resolve(root)
        if not os.path.isdir(base):
            return f"错误：目录不存在：{root}"
        matches = []
        for current, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS]
            for name in sorted(files):
                full = os.path.join(current, name)
                rel_to_base = os.path.relpath(full, base)
                if _match_glob(rel_to_base, pattern):
                    matches.append(os.path.relpath(full, self.root).replace(os.sep, "/"))
                    if len(matches) >= self.max_results:
                        matches.append(f"...（已达上限 {self.max_results}）")
                        return "\n".join(matches)
        return "\n".join(matches) if matches else "未找到匹配文件"

    def grep(
        self,
        pattern: str,
        root: str = ".",
        include: str = None,
        context: int = 0,
        ignore_case: bool = False,
        max_results: int = 50,
    ) -> str:
        """
        在项目中按正则搜索文本
        Args:
            pattern (str): 正则表达式
            root (str): 起始目录
            include (str): 只搜索匹配该 glob 的文件名（如 *.py），默认全部
            context (int): 命中行前后的上下文行数
            ignore_case (bool): 是否忽略大小写
            max_results (int): 最大命中行数
        Returns:
            str: 命中列表，每行格式 'path:line:content'
        """
        flags = re.IGNORECASE if ignore_case else 0
        try:
            regex = re.compile(pattern, flags)
        except re.error as e:
            return f"错误：正则表达式无效：{e}"

        base = self._resolve(root)
        if not os.path.isdir(base):
            return f"错误：目录不存在：{root}"

        results = []
        for current, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS]
            for name in sorted(files):
                if include and not _match_glob(name, include):
                    continue
                full = os.path.join(current, name)
                try:
                    if os.path.getsize(full) > _MAX_SEARCH_FILE_SIZE:
                        continue
                    with open(full, "r", encoding="utf-8", newline="") as f:
                        lines = f.read().splitlines()
                except (UnicodeDecodeError, FileNotFoundError, PermissionError, OSError):
                    continue
                rel = os.path.relpath(full, self.root).replace(os.sep, "/")
                for i, line in enumerate(lines):
                    if not regex.search(line):
                        continue
                    results.append(f"{rel}:{i + 1}: {line.strip()[:200]}")
                    if context > 0:
                        for j in range(max(0, i - context), min(len(lines), i + context + 1)):
                            if j == i:
                                continue
                            results.append(f"    {j + 1}| {lines[j].strip()[:200]}")
                    if len(results) >= max_results:
                        results.append(f"...（已达上限 {max_results}）")
                        return "\n".join(results)
        return "\n".join(results) if results else "未找到匹配内容"

    # ------------------------------------------------------------------ 写入

    def write(self, path: str, content: str) -> str:
        """
        写入文件（覆盖），自动创建缺失的父目录；.py 文件写入前会做语法校验
        Args:
            path (str): 文件路径
            content (str): 完整文件内容
        Returns:
            str: 操作结果
        """
        abs_path = self._resolve(path)
        if abs_path.endswith(".py"):
            try:
                ast.parse(content)
            except SyntaxError as e:
                return f"错误：Python 语法错误，未写入：{e}"
        try:
            with _file_lock(abs_path):
                self._atomic_write(abs_path, content)
        except OSError as e:
            return f"错误：写入失败：{e}"
        return f"已写入 {path}（{len(content.splitlines())} 行，{len(content)} 字符）"

    def edit(self, path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
        """
        对文件做精确文本替换（局部编辑）
        Args:
            path (str): 目标文件路径
            old_string (str): 要被替换的原文（需与文件内容一致，含缩进；\\n 与 \\r\\n 自动视为等价）
            new_string (str): 替换后的新文本
            replace_all (bool): old_string 出现多次时是否全部替换，默认 False
        Returns:
            str: 操作结果；成功时附带 unified diff

        换行兼容：匹配按 LF 归一化进行，因此 CRLF（Windows）文件也能用 \\n 的
        old_string 命中；写回时统一使用文件原本的换行符。
        """
        if not old_string:
            return "错误：old_string 不能为空"
        if old_string == new_string:
            return "错误：old_string 与 new_string 相同"

        abs_path = self._resolve(path)
        # 整段「读-改-写」持文件锁：同一条消息里并发的多个 code_edit 会串行执行，
        # 后一个编辑基于前一个写回后的内容，避免相互覆盖。
        with _file_lock(abs_path):
            try:
                with open(abs_path, "r", encoding="utf-8", newline="") as f:
                    content = f.read()
            except FileNotFoundError:
                return f"错误：文件不存在：{path}"
            except UnicodeDecodeError:
                return f"错误：二进制或非 UTF-8 文件：{path}"
            except OSError as e:
                return f"错误：读取失败：{e}"

            # 换行兼容：按 LF 归一化后再匹配，CRLF 文件也能用 \n 的 old_string。
            eol = "\r\n" if "\r\n" in content else ("\r" if "\r" in content else "\n")
            norm_content = content.replace("\r\n", "\n").replace("\r", "\n")
            norm_old = old_string.replace("\r\n", "\n").replace("\r", "\n")
            norm_new = new_string.replace("\r\n", "\n").replace("\r", "\n")

            count = norm_content.count(norm_old)
            if count == 0:
                return (
                    "错误：未找到 old_string（请确认精确文本，含缩进与换行）。\n"
                    + self._nearest_hint(content, old_string)
                )
            if count > 1 and not replace_all:
                return (
                    f"错误：old_string 在文件中出现 {count} 次，无法确定位置。"
                    "请提供更多上下文使其唯一，或设置 replace_all=True。"
                )

            new_content = norm_content.replace(
                norm_old, norm_new, -1 if replace_all else 1
            ).replace("\n", eol)

            # 写前再读一次：若已被外部（编辑器等）改动则中止，避免覆盖别人的修改
            try:
                with open(abs_path, "r", encoding="utf-8", newline="") as f:
                    latest = f.read()
            except OSError:
                latest = content
            if latest != content:
                return (
                    "错误：文件在本次编辑期间被外部修改，已中止。"
                    "请先 code_read 确认最新内容后再重试。"
                )

            try:
                self._atomic_write(abs_path, new_content)
            except OSError as e:
                return f"错误：写入失败：{e}"

        replaced = count if replace_all else 1
        diff = _unified_diff(content, new_content, path, self.max_diff_chars)
        return f"已编辑 {path}（替换 {replaced} 处）\n{diff}"

    def patch(self, path: str, patch: str) -> str:
        """
        应用 unified diff 补丁（git diff / patch 那种文本），一次可改同一文件多处
        Args:
            path (str): 目标文件路径
            patch (str): unified diff 文本（含 @@ -a,b +c,d @@ hunk，可含多个 hunk）
        Returns:
            str: 操作结果；成功时附带 unified diff

        与 code_edit 相比，适合「同一文件多处、跨行的改动」一次提交。hunk 的行号
        允许与当前文件有偏差（补丁可能基于旧版本生成），只要上下文能对上就应用；
        任一 hunk 的上下文对不上则整体失败、**文件保持原样**（不会改一半）。
        ``---``/``+++`` 等文件头会被忽略，始终以传入的 ``path`` 为准。
        """
        if not patch or not patch.strip():
            return "错误：patch 不能为空"

        try:
            hunks = _parse_unified_diff(patch)
        except ValueError as e:
            return f"错误：补丁格式无效：{e}"
        if not hunks:
            return (
                "错误：未解析到任何 hunk。补丁需包含 @@ -a,b +c,d @@ 格式的 hunk"
                "（unified diff）。"
            )

        abs_path = self._resolve(path)
        # 整段「读-改-写」持文件锁，和 code_edit 一致：同一条消息里并发的编辑串行执行。
        with _file_lock(abs_path):
            try:
                with open(abs_path, "r", encoding="utf-8", newline="") as f:
                    content = f.read()
            except FileNotFoundError:
                return f"错误：文件不存在：{path}"
            except UnicodeDecodeError:
                return f"错误：二进制或非 UTF-8 文件：{path}"
            except OSError as e:
                return f"错误：读取失败：{e}"

            # 换行兼容：按 LF 归一化后处理，写回时恢复文件原本的换行符。
            eol = "\r\n" if "\r\n" in content else ("\r" if "\r" in content else "\n")
            norm = content.replace("\r\n", "\n").replace("\r", "\n")
            had_trailing_nl = norm.endswith("\n")
            if norm == "":
                lines: list[str] = []
            else:
                lines = norm.split("\n")
                if had_trailing_nl:
                    lines = lines[:-1]

            new_lines, failed_idx = _apply_hunks(lines, hunks)
            if failed_idx is not None:
                hunk = hunks[failed_idx]
                return (
                    f"错误：第 {failed_idx + 1} 个 hunk "
                    f"（@@ -{hunk['old_start']},{hunk['old_count']} "
                    f"+{hunk['new_start']},{hunk['new_count']} @@）"
                    "的上下文与文件不匹配，已中止，文件未做任何修改。"
                    "请用 code_read 确认最新内容后重试。"
                )

            new_norm = "\n".join(new_lines)
            if had_trailing_nl and new_lines:
                new_norm += "\n"
            new_content = new_norm.replace("\n", eol)

            # 写前再读一次：若已被外部（编辑器等）改动则中止，避免覆盖别人的修改
            try:
                with open(abs_path, "r", encoding="utf-8", newline="") as f:
                    latest = f.read()
            except OSError:
                latest = content
            if latest != content:
                return (
                    "错误：文件在本次编辑期间被外部修改，已中止。"
                    "请先 code_read 确认最新内容后再重试。"
                )

            if new_content == content:
                return f"补丁未产生任何变化：{path}"

            try:
                self._atomic_write(abs_path, new_content)
            except OSError as e:
                return f"错误：写入失败：{e}"

        diff = _unified_diff(content, new_content, path, self.max_diff_chars)
        return f"已应用补丁 {path}（{len(hunks)} 个 hunk）\n{diff}"

    # ------------------------------------------------------------------ 执行

    def bash(self, command: str, cwd: str = None, timeout: int = 60) -> str:
        """
        在终端执行命令，返回输出（长输出会做首尾截断）
        Args:
            command (str): 要执行的命令
            cwd (str): 工作目录（相对项目根或绝对路径），默认项目根
            timeout (int): 超时时间（秒）默认为60s
        Returns:
            str: 命令输出与退出码
        """
        if self.sandbox is not None:
            return self._truncate(self.sandbox.execute(command, timeout=timeout))

        workdir = self._resolve(cwd) if cwd else self.root
        try:
            if platform.system() == "Windows":
                completed = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", command],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout,
                    cwd=workdir,
                )
            else:
                completed = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout,
                    cwd=workdir,
                )
        except subprocess.TimeoutExpired:
            return f"错误：命令执行超时（{timeout} 秒）"
        except Exception as e:  # noqa: BLE001
            return f"错误：命令执行失败：{e}"

        output = ((completed.stdout or "") + (completed.stderr or "")).strip()
        if not output:
            output = "（无输出）"
        return self._truncate(f"[exit {completed.returncode}]\n{output}")
