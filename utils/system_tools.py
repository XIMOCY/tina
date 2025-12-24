import os
import re
import io
import datetime
import platform
import subprocess
import time
from contextlib import redirect_stdout, redirect_stderr
from tina import Tools

system_tools = Tools()


@system_tools.register()
def get_time() -> str:
    """
    获取当前系统时间
    """
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@system_tools.register(require_confirmation=True)
def make_dir(path: str) -> str:
    """
    创建目录
    Args:
        path: 目录路径
    Returns:
        目录绝对路径
    """
    if not os.path.exists(path):
        os.makedirs(path)
    return os.path.abspath(path)


@system_tools.register()
def list_dir(path: str) -> list[str]:
    """
    列出目录下的文件和子目录
    Args:
        path: 目录路径
    Returns:
        文件和子目录名称列表
    """
    if not os.path.exists(path):
        return [f"❌ 路径不存在：{path}"]
    return os.listdir(path)


@system_tools.register()
def project_tree(root: str = ".", max_depth: int = 3) -> str:
    """
    获取项目目录结构（类似 tree 命令）
    Args:
        root: 起始目录
        max_depth: 最大递归深度
    Returns:
        目录结构字符串
    """
    root = os.path.abspath(root)
    if not os.path.exists(root):
        return f"❌ 路径不存在：{root}"

    lines: list[str] = []
    root_depth = root.count(os.sep)

    for current_root, dirs, files in os.walk(root):
        depth = current_root.count(os.sep) - root_depth
        if depth > max_depth:
            continue

        indent = "    " * depth
        rel_root = os.path.relpath(current_root, root)
        lines.append(f"{indent}{'.' if rel_root == '.' else rel_root}/")

        for name in files:
            lines.append(f"{indent}    {name}")

    return "\n".join(lines)


@system_tools.register()
def get_path(path: str) -> str:
    """
    获取一个文件或者文件夹的绝对路径
    Args:
        path: 文件或者文件夹路径
    Returns:
        文件或者文件夹的绝对路径
    """
    return os.path.abspath(path)


@system_tools.register()
def read_code(path: str, start: int = 0, end: int = 2000) -> str:
    """
    读取文件内容的片段（按字节范围）
    Args:
        path: 文件路径
        start: 起始位置（默认0）
        end: 结束位置（默认2000）
    Returns:
        文件内容片段
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return content[start:end]
    except FileNotFoundError:
        return f"文件不存在：{path}"
    except UnicodeDecodeError:
        return f"无法解码文件：{path}，请检查文件编码格式"


@system_tools.register()
def read_code_by_line(path: str, start_line: int = 1, end_line: int = 200) -> str:
    """
    按行读取代码片段
    Args:
        path: 文件路径
        start_line: 起始行（从1开始）
        end_line: 结束行（包含，默认200）
    Returns:
        指定行范围内的代码内容
    """
    if start_line < 1 or end_line < start_line:
        return "start_line 必须 >= 1 且 end_line >= start_line"
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        selected = lines[start_line - 1 : end_line]
        numbered = [f"{i+start_line}: {line}" for i, line in enumerate(selected)]
        return "".join(numbered)
    except FileNotFoundError:
        return f"文件不存在：{path}"
    except UnicodeDecodeError:
        return f"无法解码文件：{path}，请检查文件编码格式"


@system_tools.register(require_confirmation=True)
def write_code(path: str, content: str) -> str:
    """
    写入文件内容（覆盖写入）
    如果文件不存在会自动创建，但不会自动创建不存在的父目录
    Args:
        path: 文件路径
        content: 文件内容
    Returns:
        文件绝对路径
    """
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return os.path.abspath(path)


@system_tools.register(require_confirmation=True)
def append_code(path: str, content: str) -> str:
    """
    追加写入文件内容
    Args:
        path: 文件路径
        content: 追加的内容
    Returns:
        文件绝对路径
    """
    with open(path, "a", encoding="utf-8") as f:
        f.write(content)
    return os.path.abspath(path)


@system_tools.register(require_confirmation=True)
def delete_path(path: str) -> str:
    """
    删除文件或空目录
    Args:
        path: 文件或目录路径
    Returns:
        操作结果
    """
    if not os.path.exists(path):
        return f"路径不存在：{path}"

    if os.path.isdir(path):
        try:
            os.rmdir(path)
            return f"已删除空目录：{os.path.abspath(path)}"
        except OSError:
            return f"目录非空或无法删除：{os.path.abspath(path)}"
    else:
        os.remove(path)
        return f"已删除文件：{os.path.abspath(path)}"


@system_tools.register()
def search_in_files(pattern: str, root: str = ".", max_results: int = 50) -> list[str]:
    """
    在项目中搜索文本
    Args:
        pattern: 要搜索的文本（正则）
        root: 起始目录
        max_results: 最大返回结果数量
    Returns:
        命中列表，每项格式为 'path:line:content'
    """
    root = os.path.abspath(root)
    if not os.path.exists(root):
        return [f"❌ 路径不存在：{root}"]

    results: list[str] = []
    regex = re.compile(pattern)

    for current_root, _, files in os.walk(root):
        for name in files:
            path = os.path.join(current_root, name)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for idx, line in enumerate(f, start=1):
                        if regex.search(line):
                            rel = os.path.relpath(path, root)
                            results.append(f"{rel}:{idx}:{line.strip()}")
                            if len(results) >= max_results:
                                return results
            except (UnicodeDecodeError, FileNotFoundError, PermissionError):
                continue
    if not results:
        return ["未找到匹配内容"]
    return results


@system_tools.register()
def shot_down_system() -> None:
    """
    关机（Windows/Linux）
    Returns:
        None
    """
    sure = input("确定关机吗？（Y/n)")
    if sure.lower() == "y":
        if platform.system() == "Windows":
            os.system("shutdown -s -t 0")
        else:
            os.system("shutdown -h now")
    elif sure.lower() == "n":
        print("取消关机")
    else:
        print("输入错误，取消关机")
    

@system_tools.register()
def delay(seconds: int, why: str = "延迟响应") -> str:
    """
    延时函数
    Args:
        seconds: 延时秒数
        why: 延时原因
    Returns:
        延时结束提示
    """
    time.sleep(seconds)
    return f"{why}时间到了"


@system_tools.register(require_confirmation=True)
def terminal(command: str) -> str:
    """
    在终端运行指令
    Args:
        command: 指令内容
    Returns:
        指令输出
    """
    if platform.system() == "Windows":
        process = subprocess.Popen(
            ["powershell", "-Command", command],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
        )
        output, _ = process.communicate()
        return output

    else:
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            encoding="utf-8",
        )
        output, _ = process.communicate()
        return output


@system_tools.register(require_confirmation=True)
def run_python(code: str) -> str:
    """
    在受限环境中执行一小段 Python 代码
    Args:
        code: 要执行的 Python 代码字符串
    Returns:
        标准输出和最后的 result 变量（如果存在）
    使用约定:
        - 如需返回值，请在代码中赋值给变量 result
        - 例如: result = 1 + 2
    """
    buffer = io.StringIO()
    local_env: dict = {}

    try:
        with redirect_stdout(buffer), redirect_stderr(buffer):
            exec(code, {}, local_env)

        output = buffer.getvalue()
    except Exception as e:
        output = buffer.getvalue()
        output += f"\n[错误]: {repr(e)}"
        return output.strip()

    if "result" in local_env:
        output += f"\n[result] {repr(local_env['result'])}"

    return output.strip() or "代码已执行，但没有输出"

@system_tools.register(require_confirmation=True)
def replace_code_by_lines(path: str, start_line: int, end_line: int, new_content: str) -> str:
    """
    按行范围替换代码块
    Args:
        path: 目标文件路径
        start_line: 起始行（从1开始，包含）
        end_line: 结束行（包含）
        new_content: 用于替换的新代码内容（不需要带行号）
    Returns:
        操作结果或文件绝对路径
    """
    if start_line < 1 or end_line < start_line:
        return "start_line 必须 >= 1 且 end_line >= start_line"

    if not os.path.exists(path):
        return f"文件不存在：{path}"

    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        return f"无法解码文件：{path}，请检查文件编码格式"

    if start_line > len(lines):
        return f"起始行超出文件长度：文件共 {len(lines)} 行"

    end_line = min(end_line, len(lines))

    # 将新内容拆分为行，自动补充换行符
    new_lines = [line + "\n" for line in new_content.splitlines()]

    updated = lines[: start_line - 1] + new_lines + lines[end_line:]

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(updated)

    return f"已更新 {os.path.abspath(path)} 第 {start_line}-{end_line} 行"
