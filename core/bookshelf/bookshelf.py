from .book import Book
from .bookRepository import BookRepository


class BookShelf:
    """书架，可以增删更查"""

    @classmethod
    async def add_book(cls, book: Book):
        """
        将某书添加进书架
        同时添加章节列表
        """
        book.save_book_info()
        if await book.update_chapter_list():
            book.save_toc()
            return f"已将《{book.info.book_name}》加入书架。"
        else:
            return f"已将《{book.info.book_name}》加入,但章节列表拉取失败。"

    @classmethod
    def delete_book(cls, book_id: str) -> str:
        """
        从书架删除书籍
        """
        rb = BookRepository()
        try:
            rb.delete_book(book_id)
            return f"已删除书籍ID为 {book_id} 的书籍。"
        except Exception as e:
            return str(e)

    @classmethod
    async def update_book(cls, book_id: str | None) -> str:
        """
        更新书架存书
        如果不传入参数，则更新全部的书
        """
        rb = BookRepository()
        if book_id is None:
            books = rb.get_all_books()
            result = []
            for book in books:
                result.append(await book.update())
                book.save(book)
            result = "\n--------\n".join(result)
            return f"已更新书架全部书籍\n更新情况：\n{result}"
        try:
            book = BookShelf.get_book(book_id)
            result = await book.update()
            book.save()
        except Exception as e:
            return str(e)
        return f"已更新书籍《{book.info.book_name}》\n更新情况:\n{result}"

    @classmethod
    def show_book(cls, keyword: str | None) -> str:
        """
        展示书架存书
        如果存在keyword，则只展示书籍信息包含keyword的书
        """
        rb = BookRepository()
        if not keyword:
            return "书架藏书：\n\n" + "\n\n".join(
                [BookShelf.get_book(bid).info_to_str() for bid in rb.get_all_book_id()]
            )
        else:
            return "书架藏书匹配结果：\n\n" + "\n\n".join(
                [BookShelf.get_book(bid).info_to_str() for bid in rb.search_books(keyword)]
            )

    @classmethod
    def get_book(cls, book_id: str) -> Book:
        """
        通过book_id获取数据构造 Book
        """
        br = BookRepository()
        info = br.get_book_info(book_id)
        toc = br.get_all_chapters(book_id)
        contents = br.get_content_list(book_id)
        bookmark = br.get_default_bookmark(book_id)
        return Book(info, toc, contents, bookmark)