import os
import requests
from bs4 import BeautifulSoup

SERPAPI_API_KEY = "c90719ac37e34205cf4cf407f12d09f63ba5c030a83a2d6565d1b29290e1eea8"

class SerpApiSearchError(Exception):
    pass

def search_from_serpapi(query: str, num: int = 10):
    """
    使用SerpAPI进行联网搜索。
    参数：
        query (str): 搜索关键字（必需）
        num (int): 返回结果数量，默认10
    返回：
        list: 搜索结果内容列表
    """
    if not SERPAPI_API_KEY:
        raise SerpApiSearchError('请设置环境变量SERPAPI_API_KEY')
    params = {
        'q': query,
        'api_key': SERPAPI_API_KEY,
        'num': num,
        'engine': 'google',
        'hl': 'zh-cn',
        'gl': 'cn',
    }
    url = 'https://serpapi.com/search'
    resp = requests.get(url, params=params)
    if resp.status_code != 200:
        raise SerpApiSearchError(f'SerpAPI请求失败: {resp.status_code}, {resp.text}')
    data = resp.json()
    results = []
    # 解析organic_results
    for item in data.get('organic_results', [])[:num]:
        content = {
            'title': item.get('title'),
            'link': item.get('link'),
            'snippet': item.get('snippet')
        }
        results.append(content)
    return results 

def get_web_content(urls):
    """
    获取指定网页（或网页列表）的正文内容，通过这个来获取更加详细的搜索结果。
    参数：
        urls (str | list): 单个网页链接或链接列表
    返回：
        str 或 list: 主内容文本或文本列表
    """
    def fetch(url):
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding
        except Exception as e:
            return f"请求失败: {e}"
        soup = BeautifulSoup(resp.text, 'html.parser')
        main = soup.find('main')
        if main:
            text = main.get_text(separator='\n', strip=True)
            if text:
                return text
        body = soup.find('body')
        if body:
            text = body.get_text(separator='\n', strip=True)
            if text:
                return text
        return soup.get_text(separator='\n', strip=True)

    if isinstance(urls, str):
        return fetch(urls)
    elif isinstance(urls, list):
        return [fetch(url) for url in urls]
    else:
        raise ValueError('urls参数必须为str或list[str]') 