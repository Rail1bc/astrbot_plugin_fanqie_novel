import os
import sqlite3
from contextlib import contextmanager
from typing import List

from .book_info import BookInfo, ChapterInfo, ContentInfo


class BookRepository:
    """书架数据库管理类，封装所有表操作"""
    _instance = None
    _db_path = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
            cls._instance._init_db()
        return cls._instance

    @classmethod
    def set_db_path(cls, path: str):
        cls._db_path = path

    def _init_db(self):
        """
        初始化数据库连接，创建表结构并开启必要的 PRAGMA。
        """
        db_dir = os.path.dirname(self._db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        self.conn = sqlite3.connect(self._db_path)
        self.conn.row_factory = sqlite3.Row  # 使查询结果可像字典一样访问

        # 开启外键约束和 WAL 模式（提升并发与稳定性）
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self._create_tables()

    def close(self):
        """关闭数据库连接"""
        self.conn.close()

    @contextmanager
    def transaction(self):
        """事务上下文管理器，自动提交或回滚"""
        try:
            yield
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def _create_tables(self):
        """创建四张表（如果不存在）"""
        cursor = self.conn.cursor()

        # 书籍表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS books (
                book_id TEXT PRIMARY KEY,
                book_name TEXT NOT NULL,
                alias_name TEXT,
                original_book_name TEXT,
                author TEXT,
                abstract TEXT,
                word_number INTEGER,
                serial_count INTEGER,
                read_cnt_text TEXT,
                score REAL
            )
        """)

        # 章节表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chapters (
                book_id TEXT NOT NULL,
                idx INTEGER NOT NULL,
                item_id TEXT NOT NULL UNIQUE,
                version TEXT,
                title TEXT,
                volume_name TEXT,
                PRIMARY KEY (book_id, idx),
                FOREIGN KEY (book_id) REFERENCES books(book_id) ON DELETE CASCADE
            )
        """)
        # 为 item_id 创建索引（便于正文表查询）
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chapters_item_id ON chapters(item_id)")

        # 正文表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS contents (
                book_id TEXT NOT NULL,
                idx INTEGER NOT NULL,
                item_id TEXT PRIMARY KEY,
                version TEXT,
                title TEXT,
                content TEXT NOT NULL
            )
        """)

        # 书签表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bookmarks (
                book_id TEXT NOT NULL,
                bookmark_id INTEGER NOT NULL,   -- 0 表示默认书签
                bookmark_name TEXT,
                chapter_index INTEGER NOT NULL,
                PRIMARY KEY (book_id, bookmark_id),
                FOREIGN KEY (book_id) REFERENCES books(book_id) ON DELETE CASCADE
            )
        """)

        self.conn.commit()

    # ---------- 书籍操作 ----------

    def sync_book_info(self, book_info: BookInfo) -> None:
        """
        同步书籍信息到数据库（插入或更新）。
        若书籍不存在则插入，若存在则更新所有字段。
        首次插入时自动创建默认书签（bookmark_id=0）。
        """
        info = book_info
        with self.transaction():
            # 插入或替换书籍信息
            self.conn.execute("""
                INSERT OR REPLACE INTO books (
                    book_id, book_name, alias_name, original_book_name,
                    author, abstract, word_number, serial_count, read_cnt_text, score
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                info.book_id,
                info.book_name,
                info.alias_name,
                info.original_book_name,
                info.author,
                info.abstract,
                info.word_number,
                info.serial_count,
                info.read_cnt_text,
                info.score
            ))

            # 确保默认书签存在（仅当书籍首次添加时生效）
            self.conn.execute("""
                INSERT OR IGNORE INTO bookmarks (book_id, bookmark_id, bookmark_name, chapter_index)
                VALUES (?, 0, '上次阅读', 1)
            """, (info.book_id,))

    def get_book_info(self, book_id: str) -> "BookInfo":
        """获取单本书籍信息，返回 Book 对象"""
        cursor = self.conn.execute("SELECT * FROM books WHERE book_id = ?", (book_id,))
        return BookInfo.from_dict(dict(cursor.fetchone()))

    def search_books(self, keyword: str) -> List[str]:
        """根据关键词搜索，任意条目包含关键词则算匹配"""
        query = """
                SELECT book_id FROM books
                WHERE book_name LIKE ?
                   OR alias_name LIKE ?
                   OR original_book_name LIKE ?
                   OR author LIKE ?
                   OR abstract LIKE ?
            """
        pattern = f"%{keyword}%"
        cursor = self.conn.execute(query, (pattern, pattern, pattern, pattern, pattern))
        books = []
        for row in cursor:
            books.append(row["book_id"])
        return books


    def get_all_book_id(self) -> List[str]:
        """获取所有书籍列表（按添加顺序），返回每本书"""
        cursor = self.conn.execute("SELECT book_id FROM books")
        books = []
        for row in cursor:
            books.append(row['book_id'])
        return books

    def delete_book(self, book_id: str):
        """删除书籍及其关联的章节、正文、书签（外键级联删除）"""
        with self.transaction():
            self.conn.execute("DELETE FROM books WHERE book_id = ?", (book_id,))
        return f"已执行删除命令。"

    # ---------- 章节操作 ----------

    def sync_chapters(self, book_id: str, chapter_list: List[ChapterInfo]) -> None:
        """
        将 book.chapter_list 同步到数据库。
        使用 INSERT OR REPLACE 实现插入或更新。
        """
        data = [
            (book_id, idx, chapter.item_id, chapter.version, chapter.title, chapter.volume_name)
            for idx, chapter in enumerate(chapter_list, start=1)
        ]
        with self.transaction():
            self.conn.executemany("""
                        INSERT OR REPLACE INTO chapters (book_id, idx, item_id, version, title, volume_name)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, data)

    def get_chapters(self, book_id: str, offset: int = 1, limit: int = 100) -> list[ChapterInfo]:
        """
        分页获取某本书的章节列表，按 idx 排序。
        offset: 从 0 开始的偏移量（对应 idx-1）
        limit: 每页数量，默认 100
        """
        # offset 是行偏移，对应 idx 从 offset+1 开始
        offset = offset - 1
        cursor = self.conn.execute(
            "SELECT * FROM chapters WHERE book_id = ? ORDER BY idx LIMIT ? OFFSET ?",
            (book_id, limit, offset)
        )
        return [ChapterInfo.from_dict(dict(row)) for row in cursor]

    def get_all_chapters(self, book_id: str) -> List[ChapterInfo]:
        """获取某本书的全部章节（按 idx 排序）"""
        cursor = self.conn.execute(
            "SELECT * FROM chapters WHERE book_id = ? ORDER BY idx",
            (book_id,)
        )
        return [ChapterInfo.from_dict(dict(row)) for row in cursor]

    def get_chapter(self, book_id: str, idx: int) -> ChapterInfo:
        """根据书籍 ID 和章节索引获取单个章节信息"""
        cursor = self.conn.execute(
            "SELECT * FROM chapters WHERE book_id = ? AND idx = ?", (book_id, idx)
        )
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"Chapter not found: book_id={book_id}, idx={idx}")
        return ChapterInfo.from_dict(dict(row))

    # ---------- 正文操作 ----------
    def sync_content(self, book_id: str, content_list: List[ContentInfo]) -> None:
        """
        将 book.content_list 同步到数据库。
        使用 INSERT OR REPLACE 实现插入或更新。
        """
        data = [
            (book_id, idx, content.item_id, content.version, content.title, content.content)
            for idx, content in enumerate(content_list, start=1)
        ]
        with self.transaction():
            self.conn.executemany("""
                        INSERT OR REPLACE INTO contents (book_id, idx, item_id, version, title, content)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, data)

    def get_content_list(self, book_id: str) -> List[ContentInfo]:
        """获取某书的正文列表，并按章节索引排序"""
        cursor = self.conn.execute("SELECT * FROM contents WHERE book_id = ? ORDER BY idx", (book_id,))
        return [ContentInfo.from_db_dict(dict(row)) for row in cursor]

    def get_content(self, item_id: str) -> ContentInfo:
        """获取章节正文"""
        cursor = self.conn.execute("SELECT * FROM contents WHERE item_id=?", (item_id,))
        row = cursor.fetchone()
        return ContentInfo.from_db_dict(dict(row))

    # ---------- 书签操作 ----------
    def get_default_bookmark(self, book_id: str) -> int:
        """获取默认书签（当前阅读进度）对应的章节下标，若不存在则返回 1"""
        cursor = self.conn.execute(
            "SELECT chapter_index FROM bookmarks WHERE book_id=? AND bookmark_id=0", (book_id,)
        )
        row = cursor.fetchone()
        return row['chapter_index'] if row else 1

    def update_default_bookmark(self, book_id: str, chapter_index: int) -> None:
        """更新默认书签（当前阅读进度）"""
        with self.transaction():
            self.conn.execute("""
                INSERT OR REPLACE INTO bookmarks (book_id, bookmark_id, bookmark_name, chapter_index)
                VALUES (?, 0, '上次阅读', ?)
            """, (book_id, chapter_index))
