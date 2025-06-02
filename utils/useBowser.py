import httpx
import os
import time
from urllib.parse import urljoin, urlparse
from tqdm import tqdm
import re
import logging
import threading
import queue
from datetime import datetime

# 全局队列和状态变量
command_queue = queue.Queue()
result_queue = queue.Queue()
browser_status = {"running": False, "current_url": None, "last_error": None}
browser_lock = threading.Lock()

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("simple_browser")

def update_status(key, value):
    """更新浏览器状态（线程安全）"""
    with browser_lock:
        browser_status[key] = value

def get_status(key=None):
    """获取浏览器状态（线程安全）"""
    with browser_lock:
        if key:
            return browser_status.get(key)
        return browser_status.copy()

def browser_worker():
    """浏览器后台工作线程"""
    session = httpx.Client(headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    })
    current_page = None
    
    update_status("running", True)
    
    while get_status("running"):
        try:
            # 非阻塞获取命令，超时0.5秒
            try:
                cmd = command_queue.get(timeout=0.5)
            except queue.Empty:
                continue
                
            # 处理命令
            action = cmd.get("action")
            params = cmd.get("params", {})
            cmd_id = cmd.get("id", "unknown")
            
            
            if action == "navigate":
                url = params.get("url")
                try:
                    response = session.get(url, timeout=30.0)
                    response.raise_for_status()
                    current_page = response.text
                    update_status("current_url", url)
                    result_queue.put({
                        "id": cmd_id,
                        "success": True,
                        "data": {"url": url, "status_code": response.status_code}
                    })
                except Exception as e:
                    update_status("last_error", str(e))
                    result_queue.put({
                        "id": cmd_id,
                        "success": False,
                        "error": str(e)
                    })
            
            elif action == "get_page_content":
                if current_page:
                    result_queue.put({
                        "id": cmd_id,
                        "success": True,
                        "data": {"content": current_page}
                    })
                else:
                    result_queue.put({
                        "id": cmd_id,
                        "success": False,
                        "error": "No page loaded"
                    })
            
            elif action == "find_elements":
                selector = params.get("selector")
                get_text = params.get("get_text", False)
                
                if not current_page:
                    result_queue.put({
                        "id": cmd_id,
                        "success": False,
                        "error": "No page loaded"
                    })
                    continue
                    
                try:
                    # 使用正则表达式查找元素
                    pattern = re.compile(f'<{selector}[^>]*>(.*?)</{selector}>', re.DOTALL)
                    elements = pattern.findall(current_page)
                    
                    if get_text:
                        result = [re.sub('<[^<]+?>', '', elem).strip() for elem in elements]
                    else:
                        result = elements
                        
                    result_queue.put({
                        "id": cmd_id,
                        "success": True,
                        "data": {"elements": result}
                    })
                except Exception as e:
                    result_queue.put({
                        "id": cmd_id,
                        "success": False,
                        "error": str(e)
                    })
            
            elif action == "find_links":
                pattern = params.get("pattern")
                
                if not current_page:
                    result_queue.put({
                        "id": cmd_id,
                        "success": False,
                        "error": "No page loaded"
                    })
                    continue
                
                try:
                    # 使用正则表达式查找链接
                    link_pattern = re.compile(r'<a [^>]*href=["\"](.*?)["\"][^>]*>(.*?)</a>', re.DOTALL)
                    links = []
                    current_url = get_status("current_url")
                    
                    for match in link_pattern.findall(current_page):
                        url, text = match
                        url = urljoin(current_url, url)
                        text = re.sub('<[^<]+?>', '', text).strip()
                        
                        if pattern and not re.search(pattern, url):
                            continue
                            
                        links.append({"text": text, "url": url})
                        
                    result_queue.put({
                        "id": cmd_id,
                        "success": True,
                        "data": {"links": links}
                    })
                except Exception as e:
                    result_queue.put({
                        "id": cmd_id,
                        "success": False,
                        "error": str(e)
                    })
            
            elif action == "download_file":
                url = params.get("url")
                save_path = params.get("save_path", "downloads")
                filename = params.get("filename")
                
                try:
                    if not filename:
                        filename = os.path.basename(urlparse(url).path)
                        if not filename or '.' not in filename:
                            filename = f"download_{int(time.time())}.pdf"
                    
                    os.makedirs(save_path, exist_ok=True)
                    filepath = os.path.join(save_path, filename)
                    
                    
                    with session.stream("GET", url, timeout=30.0) as response:
                        response.raise_for_status()
                        
                        total_size = int(response.headers.get('content-length', 0))
                        
                        with open(filepath, 'wb') as f:
                            for chunk in response.iter_bytes(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                    
                    result_queue.put({
                        "id": cmd_id,
                        "success": True,
                        "data": {"filepath": filepath}
                    })
                except Exception as e:
                    result_queue.put({
                        "id": cmd_id,
                        "success": False,
                        "error": str(e)
                    })
            
            elif action == "exit":
                update_status("running", False)
                result_queue.put({
                    "id": cmd_id,
                    "success": True,
                    "data": {"message": "Browser thread shutting down"}
                })
                break
                
            else:
                result_queue.put({
                    "id": cmd_id,
                    "success": False,
                    "error": f"Unknown action: {action}"
                })
                
        except Exception as e:
            logger.error(f"浏览器线程错误: {str(e)}")
            update_status("last_error", str(e))
    
    logger.info("浏览器后台线程已停止")

# 工具函数 - 这些将被注册到Tina

def start_browser():
    """启动浏览器后台线程。

    启动一个后台线程来处理浏览器操作，支持网页导航、内容提取和下载功能。
    如果浏览器线程已经在运行，则不会重复启动。

    Returns:
        dict: 包含操作结果的字典，成功返回{"success": True, "message": "浏览器已启动"}
    """
    if get_status("running"):
        return {"success": True, "message": "浏览器已经在运行"}
    
    browser_thread = threading.Thread(target=browser_worker, daemon=True)
    browser_thread.start()
    
    # 等待线程启动
    time.sleep(1)
    
    return {"success": True, "message": "浏览器后台线程已启动"}

def stop_browser():
    """停止浏览器后台线程。

    安全地关闭后台浏览器线程，释放相关资源。
    如果浏览器未运行，则不执行任何操作。

    Returns:
        dict: 包含操作结果的字典，成功返回{"success": True, "message": "浏览器已停止"}
    """
    if not get_status("running"):
        return {"success": True, "message": "浏览器未运行"}
    
    cmd_id = f"cmd_{int(time.time())}"
    command_queue.put({"id": cmd_id, "action": "exit"})
    
    # 等待线程停止
    timeout = 5
    start_time = time.time()
    while get_status("running") and time.time() - start_time < timeout:
        time.sleep(0.1)
    
    if get_status("running"):
        return {"success": False, "error": "浏览器线程未能在超时时间内停止"}
    
    return {"success": True, "message": "浏览器已停止"}

def send_command(action, params=None):
    """发送命令到浏览器线程并等待响应"""
    if not get_status("running"):
        return {"success": False, "error": "浏览器未运行"}
    
    cmd_id = f"cmd_{int(time.time())}_{action}"
    command_queue.put({"id": cmd_id, "action": action, "params": params or {}})
    
    # 等待响应
    timeout = 30  # 30秒超时
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            result = result_queue.get(timeout=0.5)
            if result.get("id") == cmd_id:
                return result
            else:
                # 如果不是我们要的响应，放回队列
                result_queue.put(result)
        except queue.Empty:
            continue
    
    return {"success": False, "error": "等待响应超时"}

def navigate_to(url):
    """导航到指定URL。

    使用轻量级浏览器访问指定的网页URL。

    Args:
        url: 要访问的网页URL。

    Returns:
        dict: 包含操作结果的字典，成功返回{"success": True, "data": {"url": url, "status_code": code}}
    """
    return send_command("navigate", {"url": url})

def get_current_page():
    """获取当前页面内容。

    获取当前加载页面的HTML内容。

    Returns:
        dict: 包含操作结果的字典，成功返回{"success": True, "data": {"content": html_content}}
    """
    return send_command("get_page_content")

def find_elements(selector, get_text=False):
    """查找页面元素。

    使用CSS选择器在当前页面中查找HTML元素。

    Args:
        selector: CSS选择器字符串，用于定位元素。
        get_text: 是否只返回元素的文本内容而非HTML。默认为False。

    Returns:
        dict: 包含操作结果的字典，成功返回{"success": True, "data": {"elements": elements}}
    """
    return send_command("find_elements", {"selector": selector, "get_text": get_text})

def find_links(pattern=None):
    """查找页面链接。

    在当前页面中查找所有链接，可选择性地通过正则表达式筛选URL。

    Args:
        pattern: 可选，用于匹配链接URL的正则表达式模式。

    Returns:
        dict: 包含操作结果的字典，成功返回{"success": True, "data": {"links": links}}
    """
    return send_command("find_links", {"pattern": pattern})

def download_file(url, save_path="downloads", filename=None):
    """下载文件。

    从指定URL下载文件并保存到本地。

    Args:
        url: 文件的URL地址。
        save_path: 保存文件的目录路径，默认为"downloads"。
        filename: 可选，保存的文件名。如果未指定，将从URL中提取。

    Returns:
        dict: 包含操作结果的字典，成功返回{"success": True, "data": {"filepath": filepath}}
    """
    return send_command("download_file", {"url": url, "save_path": save_path, "filename": filename})

def search_arxiv(query, max_results=10):
    """搜索arXiv论文。

    在arXiv上搜索符合查询条件的论文。

    Args:
        query: 搜索关键词或查询字符串。
        max_results: 返回的最大结果数量，默认为10。

    Returns:
        dict: 包含操作结果的字典，成功返回{"success": True, "data": {"results": papers}}
    """
    return send_command("search_arxiv", {"query": query, "max_results": max_results})

def get_browser_status():
    """获取浏览器状态。

    获取当前浏览器线程的运行状态信息。

    Returns:
        dict: 包含浏览器状态的字典，如{"running": True, "current_url": "https://example.com"}
    """
    return get_status()

# 在导入模块时自动启动浏览器线程
if __name__ != "__main__":
    start_browser()
    logger.info("浏览器后台线程已自动启动") 