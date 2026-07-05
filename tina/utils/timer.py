import time
import functools
from tina.core import logger


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


def stream_timer(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        name = func.__qualname__
        start = time.time()
        result = func(*args, **kwargs)

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
