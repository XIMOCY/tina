import time
import functools
from tina.core import logger  # 用全局 logger 实例

# 一般同步函数 / 方法计时
def timer(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        name = func.__qualname__
        start = time.time()
        try:
            return func(*args, **kwargs)
        finally:
            end = time.time()
            logger.info(f"{name} 耗时: {end - start:.2f}秒")
    return wrapper


# 同步“流式”（返回同步生成器 / 可迭代）的计时
def stream_timer(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        name = func.__qualname__
        start = time.time()
        result = func(*args, **kwargs)  # 这里期望是生成器或可迭代对象

        def generator():
            try:
                for item in result:
                    yield item
            finally:
                end = time.time()
                logger.info(f"{name} 流式耗时: {end - start:.2f}秒")
        return generator()
    return wrapper


# 异步“流式”（返回异步生成器）的计时
def async_stream_timer(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        name = func.__qualname__
        start = time.time()
        # 这里 func 是 async 函数，返回一个异步生成器 / 异步可迭代对象
        result = await func(*args, **kwargs)

        async def agen():
            try:
                async for item in result:
                    yield item
            finally:
                end = time.time()
                logger.info(f"{name} 异步流式耗时: {end - start:.2f}秒")
        return agen()
    return wrapper
