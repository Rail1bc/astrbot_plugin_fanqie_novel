from astrbot.api.event import AstrMessageEvent

from ..bookshelf.book import Book
from ...core.bookshelf.bookshelf import BookShelf
from ...rain_api.rain_tomato_api import RainTomatoAPI

class BookShelfCommandHandle:

    # ---------- 搜书 -----------
    @staticmethod
    async def novel_search(event: AstrMessageEvent):
        """根据关键词搜索小说 /搜书 <关键词> [页码|0]"""
        # 解析参数
        args = event.message_str.split()
        if (args is None) or (len(args) < 2):
            return event.plain_result("请提供搜索关键词，格式：\n/搜书 <关键词> [页码|0]")
        keywords = args[1]
        page = int(args[2]) if len(args) > 2 and args[2].isdigit() else 0

        # 调用API搜索书籍
        api = await RainTomatoAPI.get_instance()
        try:
            books_data = await api.search(keywords, page)
        except Exception as e:
            return f"搜索请求失败:\n{e}"
        book_list = Book.list_from_dict(books_data)

        # 处理结果
        result = (
            "搜索结果：\n----------\n" +
            "\n----------\n".join(
                [f"{i + 1}. {book.book_info_to_str()}" for i, book in enumerate(book_list)]
            )
        )
        return event.plain_result(result)

    # ---------- 加书架 -----------
    @staticmethod
    async def add_book2shelf(event: AstrMessageEvent, bookshelf: BookShelf):
        """将书籍加入到书架 /加书架 <book_id>"""
        # 解析参数
        args = event.message_str.split()
        if (args is None) or (len(args) < 2):
            return event.plain_result("请提供书籍ID，格式：\n/加书架 <book_id>")
        book_id = args[1]

        # 构造Book并存入书架
        book_or_msg = await BookShelfCommandHandle._search_book_by_id(book_id)
        if isinstance(book_or_msg, str):
            return book_or_msg
        book: Book = book_or_msg
        result = await bookshelf.add_book(book)
        return event.plain_result(result)

    # ----------- 删除书籍 ------------
    @staticmethod
    def remove_book(event: AstrMessageEvent, bookshelf: BookShelf):
        """删除书籍 /删书 <book_id>"""
        args = event.message_str.split()
        if (args is None) or (len(args) < 2):
            return event.plain_result("请提供书籍ID，格式：\n/删书 <book_id>")
        book_id = args[1]
        return event.plain_result(bookshelf.DB.delete_book(book_id))

    # ---------- 更新书架 ------------
    @staticmethod
    async def update_bookshelf(event: AstrMessageEvent, bookshelf: BookShelf):
        """更新书架内容 /更新书架 [book_id]"""
        args = event.message_str.split()
        book_id = args[1] if len(args) > 1 else None
        result = await bookshelf.update_book(book_id)
        return event.plain_result(result)

    # ---------- 展示书架 -----------
    @staticmethod
    async def bookshelf_show(event: AstrMessageEvent, bookshelf: BookShelf):
        """展示书架内容 /看书架 [关键词]"""
        args = event.message_str.split()
        keyword = args[1] if len(args) > 1 else None
        result = bookshelf.show_book(keyword)
        return event.plain_result(result)

    # ---------- 看目录 ------------
    @staticmethod
    async def show_book_toc(event: AstrMessageEvent, bookshelf: BookShelf):
        """展示书籍目录 /看目录 <book_id> [页码|0]"""
        args = event.message_str.split()
        if (args is None) or (len(args) < 2):
            return event.plain_result("请提供书籍ID，格式：\n/看目录 <book_id> [页码|0]")
        book_id = args[1]
        page = int(args[2]) if len(args) > 2 and args[2].isdigit() else 0
        chapters = bookshelf.get_chapters(book_id, page)
        result = "章节列表:\n" + "\n".join([f"{i+1}: {chapter.title}" for i, chapter in enumerate(chapters)])
        return event.plain_result(result)

    # --------- 辅助方法
    @staticmethod
    async def _search_book_by_id(book_id: str) -> Book | str:
        try:
            return await Book.from_bookid(book_id)
        except TypeError as e:
            return str(e)