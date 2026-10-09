"""Files API 客户端（DeepSeek / OpenAI 兼容）

把图片上传到服务端换取 ``file_id``（形如 ``file-api-xxxxxxxx``），之后在
Chat Completions / Responses 请求里用 ``{"type": "file", "file_id": ...}``
内容块引用即可，无需每次都内联 base64：请求体更小、更省 token，且单图上限由
32 MiB 放宽到 64 MiB。

本模块只负责「上传 / 查询 / 列表 / 删除 / 本地缓存」，不负责把 file_id 拼进
消息内容块（那属于 multimodal_formatter 的职责）。

用法::

    files = FilesAPI()                      # 从 .env / tina.env 读取 key 与 base_url
    fid = files.upload_cached("a.png")      # 返回 file_id
    files.delete(fid)
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any

import httpx

from ..core import logger
from ..core.error import APIRequestFailed
from ..utils.env_reader import EnvReader



# 支持的图片扩展名 -> MIME（官方仅支持 JPEG / PNG / GIF / WebP）
SUPPORTED_EXTENSIONS = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
}

MAX_UPLOAD_BYTES = 64 * 1024 * 1024  # 单文件 64 MiB
MAX_FILENAME_LENGTH = 512
MIN_EXPIRES_SECONDS = 3600  # 1 小时
MAX_EXPIRES_SECONDS = 2592000  # 30 天

DEFAULT_CACHE_DIR = ".tina"
DEFAULT_CACHE_FILENAME = "files_cache.json"
CACHE_EXPIRY_MARGIN_SECONDS = 60  # 快过期时提前重传





def _derive_root(base_url: str) -> str:
    """从 base_url 推导 Files API 的根地址
    """
    if not base_url or not isinstance(base_url, str):
        raise ValueError("base_url 不能为空")
    root = base_url.rstrip("/")
    suffix = "/chat/completions"
    if root.endswith(suffix):
        root = root[: -len(suffix)]
    return root.rstrip("/")


def _default_cache_path() -> str:
    """默认缓存文件：工作目录下的 .tina/files_cache.json"""
    return os.path.join(os.getcwd(), DEFAULT_CACHE_DIR, DEFAULT_CACHE_FILENAME)


def _validate_expires(seconds: Any) -> int:
    if isinstance(seconds, bool) or not isinstance(seconds, int):
        raise ValueError("expires_after 必须是整数秒")
    if seconds < MIN_EXPIRES_SECONDS or seconds > MAX_EXPIRES_SECONDS:
        raise ValueError(
            f"expires_after 必须在 {MIN_EXPIRES_SECONDS}~{MAX_EXPIRES_SECONDS} 秒之间"
        )
    return seconds


def _validate_file(file_path: Any) -> tuple[str, str, str, int]:
    """校验本地文件并返回 (绝对路径, 文件名, MIME, 字节数)"""
    if not file_path or not isinstance(file_path, str):
        raise ValueError("file_path 必须是非空字符串")

    path = os.path.abspath(file_path)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"文件不存在：{path}")

    filename = os.path.basename(path)
    if len(filename) > MAX_FILENAME_LENGTH:
        raise ValueError(f"文件名过长（>{MAX_FILENAME_LENGTH}）：{filename}")

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"不支持的图片格式：{ext or '(无扩展名)'}，"
            f"仅支持 {sorted(SUPPORTED_EXTENSIONS)}"
        )

    size = os.path.getsize(path)
    if size > MAX_UPLOAD_BYTES:
        raise ValueError(f"文件过大：{size} 字节，上限 {MAX_UPLOAD_BYTES} 字节")

    return path, filename, SUPPORTED_EXTENSIONS[ext], size


def _read_file(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _extract_api_key(llm: Any) -> str | None:
    """从已有的 LLM 对象里取 api_key（兼容私有 mangling 命名）"""
    getter = getattr(llm, "get_api_key", None)
    if callable(getter):
        try:
            return getter()
        except Exception:  # noqa: BLE001 - 取不到就回退
            pass
    return getattr(llm, "_BaseAPI__api_key", None)


class FilesAPI:
    """OpenAI 兼容的 Files API 客户端"""

    def __init__(
        self,
        api_key: str = None,
        base_url: str = None,
        env_path: str = None,
        timeout: int = 180,
        use_cache: bool = True,
        cache_path: str = None,
        expires_after: int = None,
    ):
        """
        Args:
            api_key: API key，缺省时从 env 文件读取
            base_url: 对话接口的 base_url（根地址或含 /chat/completions 均可），缺省时从 env 读取
            env_path: env 文件路径，缺省时自动查找 cwd 的 .env / tina.env
            timeout: 请求超时（秒）
            use_cache: 是否启用「本地路径 -> file_id」缓存
            cache_path: 缓存文件路径，缺省为 cwd/.tina/files_cache.json
            expires_after: 默认文件有效期（秒），None 表示永久
        """
        self.__api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self.expires_after = expires_after

        # 未提供 env_path 时，自动查找 .env 或 tina.env
        if env_path is None:
            for candidate in (".env", "tina.env"):
                full_path = os.path.join(os.getcwd(), candidate)
                if os.path.exists(full_path):
                    env_path = full_path
                    break

        if env_path is not None and os.path.exists(env_path):
            reader = EnvReader(env_file=env_path)
            if self.__api_key is None:
                self.__api_key = reader.get_api_key()
            if self.base_url is None:
                self.base_url = reader.get_base_url()

        if not self.__api_key:
            raise ValueError(
                "FilesAPI - 未找到 API key，请通过参数 api_key 传入或创建 .env 文件并设置 api_key"
            )
        if not self.base_url:
            raise ValueError(
                "FilesAPI - 未找到 Base URL，请通过参数 base_url 传入或创建 .env 文件并设置 base_url"
            )

        self.root = _derive_root(self.base_url)
        self.files_url = f"{self.root}/files"

        self.use_cache = use_cache
        self.cache_path = cache_path or _default_cache_path()

        self._cache: dict[str, dict[str, Any]] = {}
        self._client: httpx.Client | None = None
        self._async_client: httpx.AsyncClient | None = None

        if self.use_cache:
            self._load_cache()

        logger.info(
            f"FilesAPI - 初始化完成，files_url: {self.files_url}，"
            f"缓存: {'开启' if self.use_cache else '关闭'}"
            + (f"（{self.cache_path}）" if self.use_cache else "")
        )

    # ========================== 构造辅助 ==========================
    @classmethod
    def from_llm(cls, llm: Any, **kwargs) -> "FilesAPI":
        """复用已有 LLM 对象的 api_key / base_url 构造 FilesAPI"""
        kwargs.setdefault("api_key", _extract_api_key(llm))
        kwargs.setdefault("base_url", getattr(llm, "base_url", None))
        return cls(**kwargs)

    # ========================== HTTP 客户端 ==========================
    @property
    def client(self) -> httpx.Client:
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    @property
    def aclient(self) -> httpx.AsyncClient:
        if self._async_client is None or self._async_client.is_closed:
            self._async_client = httpx.AsyncClient(timeout=self.timeout)
        return self._async_client

    def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            self._client.close()

    async def aclose(self) -> None:
        if self._async_client is not None and not self._async_client.is_closed:
            await self._async_client.aclose()

    def __enter__(self) -> "FilesAPI":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    async def __aenter__(self) -> "FilesAPI":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.aclose()

    def __repr__(self) -> str:
        return f"<FilesAPI base_url={self.base_url} cache={'on' if self.use_cache else 'off'}>"

    # ========================== 内部工具 ==========================
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.__api_key}"}

    def _build_upload_kwargs(
        self, filename: str, mime: str, content: bytes, purpose: str, expires_after: int
    ) -> tuple[dict, dict]:
        data = {"purpose": purpose}
        exp = expires_after if expires_after is not None else self.expires_after
        if exp is not None:
            exp = _validate_expires(exp)
            data["expires_after[anchor]"] = "created_at"
            data["expires_after[seconds]"] = str(exp)
        files = {"file": (filename, content, mime)}
        return data, files

    @staticmethod
    def _handle(resp: httpx.Response, url: str) -> dict:
        if resp.status_code != 200:
            raise APIRequestFailed(url, resp.status_code, resp.text)
        return resp.json()

    def _file_url(self, file_id: str) -> str:
        return f"{self.files_url}/{file_id}"

    # ========================== 上传 ==========================
    def upload(
        self,
        file_path: str,
        purpose: str = "user_data",
        expires_after: int = None,
    ) -> str:
        """上传图片，直接返回 file_id（需要完整信息用 retrieve(file_id)）"""
        path, filename, mime, _size = _validate_file(file_path)
        content = _read_file(path)
        data, files = self._build_upload_kwargs(
            filename, mime, content, purpose, expires_after
        )
        resp = self.client.post(
            self.files_url, headers=self._headers(), data=data, files=files
        )
        obj = self._handle(resp, self.files_url)
        return obj.get("id")

    async def aupload(
        self,
        file_path: str,
        purpose: str = "user_data",
        expires_after: int = None,
    ) -> str:
        path, filename, mime, _size = _validate_file(file_path)
        content = _read_file(path)
        data, files = self._build_upload_kwargs(
            filename, mime, content, purpose, expires_after
        )
        resp = await self.aclient.post(
            self.files_url, headers=self._headers(), data=data, files=files
        )
        obj = self._handle(resp, self.files_url)
        return obj.get("id")

    # ========================== 查询 / 列表 / 删除 ==========================
    def retrieve(self, file_id: str) -> dict:
        resp = self.client.get(self._file_url(file_id), headers=self._headers())
        return self._handle(resp, self._file_url(file_id))

    async def aretrieve(self, file_id: str) -> dict:
        resp = await self.aclient.get(self._file_url(file_id), headers=self._headers())
        return self._handle(resp, self._file_url(file_id))

    def exists(self, file_id: str) -> bool:
        url = self._file_url(file_id)
        resp = self.client.get(url, headers=self._headers())
        if resp.status_code == 200:
            return True
        if resp.status_code == 404:
            return False
        raise APIRequestFailed(url, resp.status_code, resp.text)

    async def aexists(self, file_id: str) -> bool:
        url = self._file_url(file_id)
        resp = await self.aclient.get(url, headers=self._headers())
        if resp.status_code == 200:
            return True
        if resp.status_code == 404:
            return False
        raise APIRequestFailed(url, resp.status_code, resp.text)

    def list(
        self,
        after: str = None,
        limit: int = None,
        order: str = None,
        purpose: str = None,
    ) -> dict:
        """列出已上传文件（分页）"""
        params: dict[str, Any] = {}
        if after is not None:
            params["after"] = after
        if limit is not None:
            params["limit"] = int(limit)
        if order is not None:
            params["order"] = order
        if purpose is not None:
            params["purpose"] = purpose
        resp = self.client.get(self.files_url, headers=self._headers(), params=params)
        return self._handle(resp, self.files_url)

    async def alist(
        self,
        after: str = None,
        limit: int = None,
        order: str = None,
        purpose: str = None,
    ) -> dict:
        params: dict[str, Any] = {}
        if after is not None:
            params["after"] = after
        if limit is not None:
            params["limit"] = int(limit)
        if order is not None:
            params["order"] = order
        if purpose is not None:
            params["purpose"] = purpose
        resp = await self.aclient.get(
            self.files_url, headers=self._headers(), params=params
        )
        return self._handle(resp, self.files_url)

    def delete(self, file_id: str) -> dict:
        url = self._file_url(file_id)
        resp = self.client.delete(url, headers=self._headers())
        return self._handle(resp, url)

    async def adelete(self, file_id: str) -> dict:
        url = self._file_url(file_id)
        resp = await self.aclient.delete(url, headers=self._headers())
        return self._handle(resp, url)

    # ========================== 带缓存的上传 ==========================
    def upload_cached(
        self,
        file_path: str,
        purpose: str = "user_data",
        expires_after: int = None,
        refresh: bool = False,
    ) -> str:
        """按内容 sha256 命中缓存则直接复用，否则上传并写入缓存；返回 file_id"""
        path, filename, mime, _size = _validate_file(file_path)
        content = _read_file(path)
        sha = _sha256(content)

        if self.use_cache and not refresh:
            entry = self._cache_get(sha)
            if entry is not None:
                logger.debug(f"FilesAPI - 缓存命中 {sha[:12]} -> {entry['file_id']}")
                return entry["file_id"]

        data, files = self._build_upload_kwargs(
            filename, mime, content, purpose, expires_after
        )
        resp = self.client.post(
            self.files_url, headers=self._headers(), data=data, files=files
        )
        obj = self._handle(resp, self.files_url)

        if self.use_cache:
            self._cache_put(sha, obj)
        return obj.get("id")

    async def aupload_cached(
        self,
        file_path: str,
        purpose: str = "user_data",
        expires_after: int = None,
        refresh: bool = False,
    ) -> str:
        path, filename, mime, _size = _validate_file(file_path)
        content = _read_file(path)
        sha = _sha256(content)

        if self.use_cache and not refresh:
            entry = self._cache_get(sha)
            if entry is not None:
                logger.debug(f"FilesAPI - 缓存命中 {sha[:12]} -> {entry['file_id']}")
                return entry["file_id"]

        data, files = self._build_upload_kwargs(
            filename, mime, content, purpose, expires_after
        )
        resp = await self.aclient.post(
            self.files_url, headers=self._headers(), data=data, files=files
        )
        obj = self._handle(resp, self.files_url)

        if self.use_cache:
            self._cache_put(sha, obj)
        return obj.get("id")

    # ========================== 查询已上传 ==========================
    def get_file_id(self, file_path: str, verify: bool = False) -> str | None:
        """返回该图片已上传的 file_id；没上传过则返回 None

        只查本地缓存、不会上传；verify=True 时额外联网确认文件仍存在。
        若要列举远端全部文件，用 list()。
        """
        path, _filename, _mime, _size = _validate_file(file_path)
        content = _read_file(path)
        sha = _sha256(content)
        entry = self._cache_get(sha)
        if entry is None:
            return None
        file_id = entry.get("file_id")
        if file_id is None:
            return None
        if verify and not self.exists(file_id):
            return None
        return file_id

    async def aget_file_id(self, file_path: str, verify: bool = False) -> str | None:
        path, _filename, _mime, _size = _validate_file(file_path)
        content = _read_file(path)
        sha = _sha256(content)
        entry = self._cache_get(sha)
        if entry is None:
            return None
        file_id = entry.get("file_id")
        if file_id is None:
            return None
        if verify and not await self.aexists(file_id):
            return None
        return file_id

    def cached_file_ids(self) -> list[str]:
        """返回本地缓存里所有已上传文件的 file_id"""
        return [e.get("file_id") for e in self._cache.values() if e.get("file_id")]

    # ========================== 缓存实现 ==========================
    def _cache_get(self, sha: str) -> dict | None:
        entry = self._cache.get(sha)
        if entry is None:
            return None
        expires_at = entry.get("expires_at")
        if expires_at is not None and time.time() >= expires_at - CACHE_EXPIRY_MARGIN_SECONDS:
            return None
        return entry

    def _cache_put(self, sha: str, obj: dict) -> None:
        entry = {
            "file_id": obj.get("id"),
            "filename": obj.get("filename"),
            "bytes": obj.get("bytes"),
            "sha256": sha,
            "uploaded_at": int(time.time()),
            "expires_at": obj.get("expires_at"),
        }
        self._cache[sha] = entry
        self._save_cache()

    def _load_cache(self) -> None:
        if not os.path.exists(self.cache_path):
            return
        try:
            with open(self.cache_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            entries = data.get("entries", {}) if isinstance(data, dict) else {}
            if isinstance(entries, dict):
                self._cache = entries
        except Exception as e:  # noqa: BLE001 - 缓存坏了不影响主流程
            logger.warning(f"FilesAPI - 读取缓存失败，忽略：{e}")

    def _save_cache(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
            tmp_path = f"{self.cache_path}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as fh:
                json.dump(
                    {"version": 1, "entries": self._cache},
                    fh,
                    ensure_ascii=False,
                    indent=2,
                )
            os.replace(tmp_path, self.cache_path)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"FilesAPI - 写入缓存失败，忽略：{e}")

    def purge_cache(self, delete_remote: bool = False) -> int:
        """清空本地缓存；delete_remote=True 时同时删除远端文件，返回清理条数"""
        count = len(self._cache)
        if delete_remote:
            for entry in self._cache.values():
                file_id = entry.get("file_id")
                if not file_id:
                    continue
                try:
                    self.delete(file_id)
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"FilesAPI - 删除远端文件失败 {file_id}：{e}")
        self._cache = {}
        if self.use_cache:
            self._save_cache()
        return count

    @property
    def cache(self) -> dict[str, dict[str, Any]]:
        """返回缓存副本"""
        return dict(self._cache)
