from concurrent.futures import ThreadPoolExecutor
import os
from datetime import datetime
from threading import Lock

def analyze_single_paper(path):
    prompt = """
    你是一个论文分析助手，你需要分析论文给出下面的内容：
        论文的相关信息
        论文的创新点
        论文的摘要
        论文的通俗概括
        论文的研究点
        实验过程
        引言
        结论
        参考文献
    注意你的最大的输入只有20000个字符，请不要超过这个限制，如果超过了请分开阅读
    """
    tools = Tools()
    tools.register(
        name="readParper",
        description="阅读论文，返回指定数字范围的文本内容比如：readParper('paper.pdf',1,10) 返回第一个字到第十个字的文本内容",
        required_parameters=["filename","start_num","end_num"],
        parameters={
            "filename": {"type": "string", "description": "论文的pdf文件名"},
            "start_num": {"type": "int", "description": "起始数字"},
            "end_num": {"type": "int", "description": "结束数字"}
        },
        path=r"D:\development\project\useTina\readParperTools.py"
    )
    read_parper_agent = Agent(
        LLM=llm,
        tools = tools,
        sys_prompt=prompt
    )
    result = read_parper_agent.predict(
        input_text=f"阅读这篇论文{path}"
    )
    content = ""
    for item in result:
        if item["role"] == "assistant":
            content += item["content"]

    return content

progress_lock = Lock()
completed_tasks = 0

def get_progress(total_tasks):
    """
    获取当前的进度百分比
    Args:
        total_tasks: 总任务数
    Returns:
        当前进度的百分比
    """
    with progress_lock:
        return (completed_tasks / total_tasks) * 100

def AnalyzeParper(paths):
    """
    读取多个论文文件，使用多线程处理，并将结果保存为Markdown文件
    Args:
        paths: 论文文件路径列表
    """
    global completed_tasks
    max_threads = 5
    results = {}
    current_date = datetime.now().strftime('%Y-%m-%d')
    base_dir = f'report/{current_date}'
    os.makedirs(base_dir, exist_ok=True)

    total_tasks = len(paths)
    completed_tasks = 0

    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        future_to_path = {executor.submit(analyze_single_paper, path): path for path in paths}
        for future in concurrent.futures.as_completed(future_to_path):
            path = future_to_path[future]
            try:
                result_content = future.result()
                results[path] = result_content

                # 获取文件名并创建Markdown文件路径
                file_name = os.path.basename(path).replace('.pdf', '_报告.md')
                report_path = os.path.join(base_dir, file_name)

                # 将结果写入Markdown文件
                with open(report_path, 'w', encoding='utf-8') as report_file:
                    report_file.write(result_content)

            except Exception as exc:
                results[path] = f'生成时出错: {exc}'
            finally:
                with progress_lock:
                    completed_tasks += 1

    return results 