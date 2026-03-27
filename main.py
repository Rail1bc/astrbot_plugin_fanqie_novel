from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

from .bookshelf.book import Book
from .rain_api.rain_tomato_api import RainTomatoAPI


@register("astrbot_plugin_fanqie_novel", "Rail1bc", "让ai读小说，我是说让ai读，不是给你读", "0.1.0")
class FanqieNovel(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self.config = config or {}

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""
        # 初始化 api
        apikey = self.config.get("rain_api_key")
        base_url = self.config.get("novel_resource_base")
        if not apikey:
            logger.warning("没有 api key ,无法更新、获取新的书籍信息。")
        else:
            api = await RainTomatoAPI.get_instance(apikey="your_key")
            logger.debug("api 初始化完成")
            books = await api.search("我的兄弟叫顺溜")

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
        await RainTomatoAPI.destroy_instance()

    @filter.command("搜书")
    async def novel_search(self, event: AstrMessageEvent):
        """根据关键词搜索小说 /搜书 <关键词> [页码|0]"""
        args = event.message_str.split()
        keywords = args[1] if len(args) > 1 else ""
        page = int(args[2]) if len(args) > 2 and args[2].isdigit() else 0
        result = await self.search_book_by_keywords(keywords, page)
        yield event.plain_result(result)










    async def search_book_by_keywords(self, keywords: str, page: int = 0) -> str:
        """根据关键字搜索小说"""
        api = await RainTomatoAPI.get_instance()

        if (api is None) or (api.enable is False):
            return "api失效，无法更新、获取新的书籍信息。"

        books_data = await api.search(keywords, page)
        book_list = Book.book_list_from_dict(books_data)

        result = ("搜索结果：\n----------\n" +
               "\n----------\n".join([f"{i+1}. {book.book_info_to_str()}" for i, book in enumerate(book_list)]))
        return result