"""tina 提供的系统工具包

按官方示例的「类 + 工具包」范式组织：类里持有 `Tools(name=...)`，
通过 `register_tool` 注册方法，并对外提供 `get_tools()`。

用法（保持向后兼容，和使用普通工具包一样）：

    from tina.utils.system_tools import system_tools

    your_tools += system_tools

也可以自己实例化/继承：

    from tina.utils.system_tools import SystemTools

    sys_tools = SystemTools()
    agent = Agent(llm=..., tools=sys_tools.get_tools())
"""

import datetime
import io
import os
import platform
import re
import shutil
import subprocess
import time
from contextlib import redirect_stderr, redirect_stdout
from typing import Protocol

from tina import Tools

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


def _ensure_parent(path: str) -> None:
    """确保文件的父目录存在"""
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)


class Sandbox(Protocol):
    """命令执行后端协议

    沙箱是**工具实现内部**的事：只要实现 `execute`，就能注入给 `SystemTools`，
    由 `terminal` 工具在内部调用（例如容器、受限 shell、远程执行环境）。
    """

    def execute(self, command: str, timeout: int = 60) -> str:
        """执行一条命令并返回输出文本"""
        ...


class LocalSandbox:
    """默认后端：直接在本机执行命令（无隔离，仅做超时与编码兜底）"""

    def execute(self, command: str, timeout: int = 60) -> str:
        try:
            if platform.system() == "Windows":
                completed = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", command],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout,
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
                )
        except subprocess.TimeoutExpired:
            return f"错误：命令执行超时（{timeout} 秒）"
        except Exception as e:
            return f"错误：命令执行失败：{e}"

        output = ((completed.stdout or "") + (completed.stderr or "")).strip()
        if not output:
            output = "（无输出）"
        return f"[exit {completed.returncode}]\n{output}"


class SystemTools:
    """系统工具包：时间、文件、目录、终端、代码执行等常用能力

    Args:
        sandbox: 命令执行后端（实现 `execute(command, timeout)`）。默认使用
            `LocalSandbox`（本机直接执行、无隔离）。传入自定义沙箱即可让
            `terminal` 工具在内部走隔离环境。
    """

    tools: Tools
    sandbox: Sandbox

    def __init__(self, sandbox: Sandbox | None = None) -> None:
        self.sandbox = sandbox if sandbox is not None else LocalSandbox()
        self.tools = Tools(name="tina_sys_tools")

        self.tools.register_tool(tool=self.get_time)
        self.tools.register_tool(tool=self.make_dir, require_confirmation=True)
        self.tools.register_tool(tool=self.list_dir)
        self.tools.register_tool(tool=self.project_tree)
        self.tools.register_tool(tool=self.get_path)
        self.tools.register_tool(tool=self.read_code)
        self.tools.register_tool(tool=self.read_code_by_line)
        self.tools.register_tool(tool=self.write_code, require_confirmation=True)
        self.tools.register_tool(tool=self.append_code, require_confirmation=True)
        self.tools.register_tool(tool=self.delete_path, require_confirmation=True)
        self.tools.register_tool(tool=self.search_in_files)
        self.tools.register_tool(
            tool=self.shot_down_system, require_confirmation=True
        )
        self.tools.register_tool(tool=self.delay)
        self.tools.register_tool(tool=self.terminal, require_confirmation=True)
        self.tools.register_tool(tool=self.run_python, require_confirmation=True)
        self.tools.register_tool(
            tool=self.replace_code_by_lines, require_confirmation=True
        )

    def get_tools(self) -> Tools:
        """把工具包公开出去"""
        return self.tools

    # ------------------------------------------------------------------ 时间

    def get_time(self) -> str:
        """
        获取当前系统时间
        Returns:
            str: 当前时间字符串，格式 YYYY-MM-DD HH:MM:SS
        """
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def delay(self, seconds: int, why: str = "延迟响应") -> str:
        """
        延时指定秒数后再返回
        Args:
            seconds (int): 延时秒数，必须 >= 0
            why (str): 延时原因
        Returns:
            str: 延时结束提示
        """
        seconds = max(0, int(seconds))
        time.sleep(seconds)
        return f"{why}时间到了（已等待 {seconds} 秒）"

    # ------------------------------------------------------------------ 目录

    def make_dir(self, path: str) -> str:
        """
        创建目录（会自动创建缺失的父目录）
        Args:
            path (str): 目录路径
        Returns:
            str: 目录绝对路径，或错误说明
        """
        abs_path = os.path.abspath(path)
        if os.path.isdir(abs_path):
            return f"目录已存在：{abs_path}"
        if os.path.exists(abs_path):
            return f"错误：已存在同名文件：{abs_path}"
        try:
            os.makedirs(abs_path, exist_ok=True)
        except OSError as e:
            return f"错误：创建失败：{e}"
        return abs_path

    def list_dir(self, path: str = ".") -> str:
        """
        列出目录下的文件和子目录（目录名以 / 结尾）
        Args:
            path (str): 目录路径，默认为当前目录
        Returns:
            str: 逐行列出，每行一个名称
        """
        abs_path = os.path.abspath(path)
        if not os.path.exists(abs_path):
            return f"错误：路径不存在：{abs_path}"
        if os.path.isfile(abs_path):
            return abs_path
        try:
            entries = sorted(os.listdir(abs_path))
        except PermissionError:
            return f"错误：无权限读取：{abs_path}"
        if not entries:
            return "（空目录）"
        return "\n".join(
            f"{name}/" if os.path.isdir(os.path.join(abs_path, name)) else name
            for name in entries
        )

    def project_tree(
        self, root: str = ".", max_depth: int = 3, max_lines: int = 500
    ) -> str:
        """
        获取项目目录结构（类似 tree 命令，自动忽略 .git/.venv/__pycache__ 等）
        Args:
            root (str): 起始目录
            max_depth (int): 最大递归深度
            max_lines (int): 最大输出行数，超出会截断
        Returns:
            str: 目录结构字符串
        """
        abs_root = os.path.abspath(root)
        if not os.path.isdir(abs_root):
            return f"错误：目录不存在：{abs_root}"

        lines: list[str] = [f"{os.path.basename(abs_root) or abs_root}/"]
        truncated = False

        def walk(directory: str, depth: int) -> None:
            nonlocal truncated
            if depth >= max_depth or len(lines) >= max_lines:
                truncated = len(lines) >= max_lines
                return
            try:
                entries = sorted(os.listdir(directory))
            except PermissionError:
                return

            dirs = [
                name
                for name in entries
                if name not in _IGNORE_DIRS
                and os.path.isdir(os.path.join(directory, name))
            ]
            files = [
                name
                for name in entries
                if os.path.isfile(os.path.join(directory, name))
            ]

            indent = "    " * (depth + 1)
            for name in dirs:
                lines.append(f"{indent}{name}/")
                if len(lines) >= max_lines:
                    truncated = True
                    return
                walk(os.path.join(directory, name), depth + 1)
                if truncated:
                    return
            for name in files:
                lines.append(f"{indent}{name}")
                if len(lines) >= max_lines:
                    truncated = True
                    return

        walk(abs_root, 0)
        if truncated:
            lines.append(f"...（已达 max_lines={max_lines}，输出截断）")
        return "\n".join(lines)

    def get_path(self, path: str) -> str:
        """
        获取一个文件或者文件夹的绝对路径
        Args:
            path (str): 文件或者文件夹路径
        Returns:
            str: 绝对路径
        """
        return os.path.abspath(path)

    # ------------------------------------------------------------------ 读取

    def read_code(self, path: str, start: int = 0, end: int = None) -> str:
        """
        读取文件内容的字符片段
        Args:
            path (str): 文件路径
            start (int): 起始字符位置，从 0 开始
            end (int): 结束字符位置（不含），默认读到文件末尾
        Returns:
            str: 文件内容片段
        """
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError:
            return f"错误：文件不存在：{path}"
        except UnicodeDecodeError:
            return f"错误：无法解码文件（非 UTF-8 文本）：{path}"
        except OSError as e:
            return f"错误：读取失败：{e}"
        return content[start:end]

    def read_code_by_line(
        self, path: str, start_line: int = 1, end_line: int = 200
    ) -> str:
        """
        按行读取代码片段，返回内容带行号
        Args:
            path (str): 文件路径
            start_line (int): 起始行，从 1 开始
            end_line (int): 结束行（包含）
        Returns:
            str: 带行号的代码内容
        """
        if start_line < 1 or end_line < start_line:
            return "错误：start_line 必须 >= 1 且 end_line >= start_line"
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except FileNotFoundError:
            return f"错误：文件不存在：{path}"
        except UnicodeDecodeError:
            return f"错误：无法解码文件（非 UTF-8 文本）：{path}"
        except OSError as e:
            return f"错误：读取失败：{e}"

        selected = lines[start_line - 1 : end_line]
        if not selected:
            return f"错误：起始行超出文件范围（文件共 {len(lines)} 行）"
        numbered = [f"{i + start_line}: {line}" for i, line in enumerate(selected)]
        return "".join(numbered)

    def search_in_files(
        self, pattern: str, root: str = ".", max_results: int = 50
    ) -> str:
        """
        在项目中按正则搜索文本
        Args:
            pattern (str): 要搜索的正则表达式
            root (str): 起始目录
            max_results (int): 最大返回命中数量
        Returns:
            str: 命中列表，每行格式为 'path:line:content'
        """
        try:
            regex = re.compile(pattern)
        except re.error as e:
            return f"错误：正则表达式无效：{e}"

        abs_root = os.path.abspath(root)
        if not os.path.isdir(abs_root):
            return f"错误：目录不存在：{abs_root}"

        results: list[str] = []
        for current_root, dirs, files in os.walk(abs_root):
            dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS]
            for name in sorted(files):
                path = os.path.join(current_root, name)
                try:
                    if os.path.getsize(path) > _MAX_SEARCH_FILE_SIZE:
                        continue
                    with open(path, "r", encoding="utf-8") as f:
                        for idx, line in enumerate(f, start=1):
                            if regex.search(line):
                                rel = os.path.relpath(path, abs_root)
                                results.append(f"{rel}:{idx}:{line.strip()[:200]}")
                                if len(results) >= max_results:
                                    return "\n".join(results)
                except (UnicodeDecodeError, FileNotFoundError, PermissionError, OSError):
                    continue

        if not results:
            return "未找到匹配内容"
        return "\n".join(results)

    # ------------------------------------------------------------------ 写入

    def write_code(self, path: str, content: str) -> str:
        """
        写入文件内容（覆盖写入，自动创建缺失的父目录）
        Args:
            path (str): 文件路径
            content (str): 要写入的完整内容
        Returns:
            str: 文件绝对路径，或错误说明
        """
        abs_path = os.path.abspath(path)
        try:
            _ensure_parent(abs_path)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(content)
        except OSError as e:
            return f"错误：写入失败：{e}"
        return abs_path

    def append_code(self, path: str, content: str) -> str:
        """
        追加写入文件内容（自动创建缺失的父目录）
        Args:
            path (str): 文件路径
            content (str): 追加的内容
        Returns:
            str: 文件绝对路径，或错误说明
        """
        abs_path = os.path.abspath(path)
        try:
            _ensure_parent(abs_path)
            with open(abs_path, "a", encoding="utf-8") as f:
                f.write(content)
        except OSError as e:
            return f"错误：写入失败：{e}"
        return abs_path

    def delete_path(self, path: str, recursive: bool = False) -> str:
        """
        删除文件或目录
        Args:
            path (str): 文件或目录路径
            recursive (bool): 目录非空时是否递归删除，默认 False（仅删空目录）
        Returns:
            str: 操作结果
        """
        abs_path = os.path.abspath(path)
        if not os.path.exists(abs_path):
            return f"错误：路径不存在：{abs_path}"
        try:
            if os.path.isdir(abs_path):
                if recursive:
                    shutil.rmtree(abs_path)
                    return f"已递归删除目录：{abs_path}"
                os.rmdir(abs_path)
                return f"已删除空目录：{abs_path}"
            os.remove(abs_path)
            return f"已删除文件：{abs_path}"
        except OSError as e:
            return f"错误：删除失败：{e}"

    def replace_code_by_lines(
        self, path: str, start_line: int, end_line: int, new_content: str
    ) -> str:
        """
        按行范围替换文件内容
        Args:
            path (str): 目标文件路径
            start_line (int): 起始行，从 1 开始（包含）
            end_line (int): 结束行（包含）
            new_content (str): 用于替换的新内容（不需要带行号）
        Returns:
            str: 操作结果
        """
        if start_line < 1 or end_line < start_line:
            return "错误：start_line 必须 >= 1 且 end_line >= start_line"

        abs_path = os.path.abspath(path)
        if not os.path.exists(abs_path):
            return f"错误：文件不存在：{abs_path}"

        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            return f"错误：无法解码文件（非 UTF-8 文本）：{abs_path}"
        except OSError as e:
            return f"错误：读取失败：{e}"

        if start_line > len(lines):
            return f"错误：起始行超出文件长度（文件共 {len(lines)} 行）"

        end_line = min(end_line, len(lines))
        new_lines = [line + "\n" for line in new_content.splitlines()]

        try:
            with open(abs_path, "w", encoding="utf-8") as f:
                f.writelines(lines[: start_line - 1] + new_lines + lines[end_line:])
        except OSError as e:
            return f"错误：写入失败：{e}"
        return f"已更新 {abs_path} 第 {start_line}-{end_line} 行"

    # ------------------------------------------------------------------ 执行

    def terminal(self, command: str, timeout: int = 60) -> str:
        """
        在终端运行指令（实际执行委托给注入的 sandbox）
        Args:
            command (str): 要执行的命令
            timeout (int): 超时时间（秒）
        Returns:
            str: 命令输出与退出码
        """
        return self.sandbox.execute(command, timeout=timeout)

    def run_python(self, code: str) -> str:
        """
        执行一小段 Python 代码，并返回其输出
        Args:
            code (str): 要执行的 Python 代码
        Returns:
            str: 标准输出；若代码中给变量 result 赋值，也会一并返回
        约定:
            - 如需返回值，请把结果赋值给变量 result，例如 result = 1 + 2
        """
        buffer = io.StringIO()
        local_env: dict = {}

        try:
            with redirect_stdout(buffer), redirect_stderr(buffer):
                exec(code, {}, local_env)
        except Exception as e:
            output = buffer.getvalue()
            output += f"\n[错误]: {repr(e)}"
            return output.strip()

        output = buffer.getvalue()
        if "result" in local_env:
            output += f"\n[result] {repr(local_env['result'])}"

        return output.strip() or "代码已执行，但没有输出"

    def shot_down_system(self) -> str:
        """
        关闭计算机（Windows/Linux）。执行前会触发工具确认事件
        Returns:
            str: 操作结果
        """
        try:
            if platform.system() == "Windows":
                os.system("shutdown -s -t 0")
            else:
                os.system("shutdown -h now")
        except Exception as e:
            return f"错误：关机失败：{e}"
        return "已发出关机指令"


system_tools = SystemTools().get_tools()
