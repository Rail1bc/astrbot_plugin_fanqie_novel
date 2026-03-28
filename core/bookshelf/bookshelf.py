from .book import Book
from .bookshelfDB import BookshelfDB



class BookShelf:
    """ 书架 """
    def __init__(self):
        self.DB = BookshelfDB()


    def add_book(self, book: Book):
        """
        将某书添加进书架
        """
        self.DB.add_book(book)

    def get_books(self, book_id: str) -> Book:
        return self.DB.get_book(book_id)