import asyncio
import logging
from typing import List, Optional, Any, Dict
from urllib.parse import urlencode

import aiohttp

logger = logging.getLogger(__name__)


class RainTomatoAPI:
    """异步番茄API客户端"""

    DEFAULT_BASE = "https://v3.rain.ink/fanqie/"

    def __init__(
        self,
        apikey: str,
        base_url: Optional[str] = None,
        timeout: int = 10,
        max_retries: int = 2,
        backoff: float = 0.3,
        session: Optional[aiohttp.ClientSession] = None,
    ):
        """
        初始化API客户端。

        :param apikey: API密钥
        :param base_url: 基地址，默认使用DEFAULT_BASE
        :param timeout: 请求超时时间（秒）
        :param max_retries: 最大重试次数（不包含首次）
        :param backoff: 重试退避基数（sleep = backoff * attempt）
        :param session: 可选的aiohttp会话，若不提供则内部创建
        """
        self.apikey = apikey
        self.base_url = base_url or self.DEFAULT_BASE
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff = backoff
        self._session = session
        self._own_session = session is None
        self.enable = True  # 乐观判断api可用

    _instance = None

    @classmethod
    async def get_instance(cls, apikey: str = None, **kwargs):
        """获取全局单例实例（首次调用时初始化）"""
        if cls._instance is None:
            cls._instance = cls(apikey=apikey, **kwargs)
            # 注意：如果使用异步上下文管理器，需要手动调用 __aenter__ 初始化会话
            await cls._instance.__aenter__()
        return cls._instance

    @classmethod
    async def destroy_instance(cls):
        """销毁单例实例，关闭会话并重置状态"""
        if cls._instance is not None:
            await cls._instance.close()  # 调用实例的close方法关闭会话
            cls._instance = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取当前会话，若未创建则创建"""
        if self._session is None:
            self._session = aiohttp.ClientSession(
                headers={
                    "User-Agent": "tomato-rain-client/1.0",
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                }
            )
        return self._session

    async def close(self):
        """关闭会话（如果由内部创建）"""
        if self._own_session and self._session:
            await self._session.close()
            self._session = None

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self._get_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        await self.close()

    async def _get(self, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        异步GET请求，带重试和错误处理。

        :param params: 请求参数（apikey会自动添加）
        :return: 解析后的JSON字典，失败时返回None
        """
        params = params.copy()
        params["apikey"] = self.apikey
        # 构建URL，处理已有查询参数的情况
        sep = "&" if "?" in self.base_url else "?"
        url = f"{self.base_url}{sep}{urlencode(params)}"

        last_err = None
        for attempt in range(1, self.max_retries + 2):
            try:
                session = await self._get_session()
                timeout = aiohttp.ClientTimeout(total=self.timeout)
                async with session.get(url, timeout=timeout) as resp:
                    resp.raise_for_status()
                    text = await resp.text()
                    # 空响应或"null"视为无数据
                    if not text or text.strip() == "null":
                        logger.warning("响应为空或null")
                        self.enable = False
                        return None
                    data = await resp.json()
                    # 检查业务状态码
                    if data.get("message") != "SUCCESS":
                        logger.warning("请求未成功: %r", data)
                        self.enable = False
                    return data
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_err = e
                logger.debug("请求失败（尝试 %d/%d）: %s", attempt, self.max_retries + 1, e)
                if attempt <= self.max_retries:
                    await asyncio.sleep(self.backoff * attempt)

        # 重试耗尽
        self.enable = False
        logger.warning("请求失败，已超过最大重试次数: %s", last_err)
        return None

    async def search(self, keywords: str, page: int = 0) -> List[Dict[str, Any]]:
        """
        搜索书籍。

        :param keywords: 搜索关键词
        :param page: 页码
        :return: 书籍列表
        """
        params = {"type": 1, "keywords": keywords, "page": page}
        data = await self._get(params)
        search_tabs = data.get("search_tabs", [])
        # 找到 tab_type 为 3 或 '3' 的 tab
        target_tab = next(
            (tab for tab in search_tabs if tab.get("tab_type") in (3, "3")),
            None,
        )
        book_list = []
        for cell in target_tab.get("data", []):
            book_data = cell.get("book_data")
            if book_data and isinstance(book_data, list) and len(book_data) > 0:
                book_list.append(book_data[0])
        return book_list

    async def book_info(self, bookid: str) -> Optional[Dict[str, Any]]:
        """
        获取书籍详细信息。

        :param bookid: 书籍ID
        :return: 书籍信息字典，失败返回None
        """
        params = {"type": 2, "bookid": bookid}
        data = await self._get(params)
        return data.get("data") if data else None

    async def toc(self, bookid: str) -> Optional[List[Dict[str, Any]]]:
        """
        获取目录（章节列表）。

        :param bookid: 书籍ID
        :return: 目录列表，失败返回None
        """
        params = {"type": 3, "bookid": bookid}
        data = await self._get(params)
        if data:
            return data.get("data", {}).get("item_data_list")
        return None

    async def chapter(self, itemid: str, tone: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        获取章节内容。

        :param itemid: 章节ID
        :param tone: 可选音调参数（原接口预留）
        :return: 章节内容字典，失败返回None
        """
        params = {"type": 4, "itemid": itemid}
        data = await self._get(params)
        return data.get("data") if data else None