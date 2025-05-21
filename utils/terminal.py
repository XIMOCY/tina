from asyncio import Queue
import os
import subprocess
import threading


def terminal(command):
    """
    在终端运行指令
    Args:
        command: 指令内容
    returns:
        指令输出
    """

    # 新增：获取当前模块所在目录
    module_dir = os.getcwd()

    def _stream_reader(pipe, queue):
        try:
            for line in iter(pipe.readline, ''):
                queue.put(line)
        finally:
            pipe.close()
            queue.put(None)  # 结束标志

    process = subprocess.Popen(
        ["powershell", "-Command", command],  # 修改：显式使用PowerShell
        shell=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        bufsize=1,
        cwd=module_dir  # 新增：设置工作目录为模块路径
    )
    
    q = Queue()
    t = threading.Thread(target=_stream_reader, args=(process.stdout, q))
    t.daemon = True
    t.start()

    output = []
    while True:
        line = q.get()  # 阻塞式获取输出
        if line is None:
            break
        output.append(line)

    t.join()  # 确保读取线程完成
    process.wait()  # 等待进程完全终止

    return ''.join(output)