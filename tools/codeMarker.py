import os
import subprocess
import threading
from queue import Queue


def writeCode(filename, code):
    path = os.path.join(os.getcwd(), filename)
    with open(filename, 'w') as f:
        f.write(code)
    return path

def readCode(filename):
    path = os.path.join(os.getcwd(), filename)
    with open(filename, 'r') as f:
        code = f.read()
    return code

def deleteCode(filename):
    path = os.path.join(os.getcwd(), filename)
    os.remove(path)
    return path


def runCode(filename):
    path = os.path.join(os.getcwd(), filename)
    
    def _run_script(output_queue):
        try:
            # 直接运行脚本不打开新窗口
            process = subprocess.Popen(
                ['python', path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8'
            )
            
            # 实时捕获输出
            stdout, stderr = process.communicate()
            output_queue.put({
                'stdout': stdout,
                'stderr': stderr,
                'returncode': process.returncode
            })
            
        except Exception as e:
            output_queue.put({'error': str(e)})

    # 创建通信队列和线程
    output_queue = Queue()
    thread = threading.Thread(target=_run_script, args=(output_queue,))
    thread.start()
    
    # 返回队列对象供主程序检查
    return output_queue
def runCodeNotOpenTerminal(code):
    try:
        result = eval(code)
        return result
    except Exception as e:
        return str(e)

