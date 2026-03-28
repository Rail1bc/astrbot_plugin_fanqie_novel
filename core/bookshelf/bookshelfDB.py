import sqlite3
from contextlib import contextmanager
from typing import List, Dict, Any, Optional
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .book import Book, ChapterInfo


class BookshelfDB:
    """书架数据库管理类，封装所有表操作"""

    def __init__(self):
        """
        初始化数据库连接，创建表结构并开启必要的 PRAGMA。
        """
        self.db_path = get_astrbot_data_path() / "plugin_data" / self.name / "bookshelf.db"
        self.conn = sqlite3.connect(self.db_path)
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
                item_id TEXT PRIMARY KEY,
                version TEXT,
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
    def add_book(self, book: Book) -> str:
        """
        添加一本书籍。
        :param book:
        :return: book_id
        """

        info = book.info
        with self.transaction():
            cursor = self.conn.cursor()
            cursor.execute("""
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

            # 为新添加的书籍创建一个默认书签（bookmark_id=0），初始章节为 1
            cursor.execute("""
                INSERT OR IGNORE INTO bookmarks (book_id, bookmark_id, bookmark_name, chapter_index)
                VALUES (?, 0, '上次阅读', 1)
            """, (book.info.book_id,))

        return book.info.book_name

    def update_book(self, book: Book) -> None:
        """更新书籍信息，传入字段名和值"""
        info = book.info
        set_clause = (
            f"book_id={info.book_id}," +
            f"book_name={info.book_name}," +
            f"alias_name={info.alias_name}," +
            f"original_book_name={info.original_book_name}," +
            f"author={info.author}," +
            f"abstract={info.abstract}," +
            f"word_number={info.word_number}," +
            f"serial_count={info.serial_count}," +
            f"read_cnt_text={info.read_cnt_text}," +
            f"score={info.score}"
        )

        with self.transaction():
            self.conn.execute(f"UPDATE books SET {set_clause} WHERE book_id=?", book.info.book_id)

    def get_book(self, book_id: str) -> Book:
        """获取单本书籍信息，返回字典或 None"""
        cursor = self.conn.execute("SELECT * FROM books WHERE book_id=?", (book_id,))
        row = cursor.fetchone()
        return Book.book_from_dict(dict(row))

    def get_all_books(self) -> List[str]:
        """获取所有书籍列表（按添加顺序）"""
        cursor = self.conn.execute("SELECT book_name FROM books")
        book_list = []
        for row in cursor:
            book_list.append(row['book_name'])
        return book_list

    def delete_book(self, book_id: str) -> None:
        """删除书籍及其关联的章节、正文、书签（外键级联删除）"""
        with self.transaction():
            self.conn.execute("DELETE FROM books WHERE book_id=?", (book_id,))

    # ---------- 章节操作 ----------
    def add_chapters(self, book: Book) -> None:
        """
        批量添加或更新章节。
        chapters 中每个字典需包含: idx, item_id, version, title, volume_name
        """
        cl = book.chapter_list
        with self.transaction():
            for ch in cl:
                self.conn.execute("""
                    INSERT OR REPLACE INTO chapters (book_id, idx, item_id, version, title, volume_name)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    book.info.book_id,
                    cl.index(ch) + 1,  # idx 从 1 开始
                    ch.item_id,
                    ch.version,
                    ch.title,
                    ch.volume_name
                ))

    def get_chapter(self, book_id: str, idx: int) -> ChapterInfo:
        """根据书籍和章节下标获取章节信息（不含正文）"""
        cursor = self.conn.execute(
            "SELECT * FROM chapters WHERE book_id=? AND idx=?", (book_id, idx)
        )
        row = cursor.fetchone()
        return ChapterInfo.from_api_dict(dict(row))

    def get_chapters_list(self, book_id: str, step: int) -> Optional[list[ChapterInfo]]:
        """
        获取某本书的章节列表，按 idx 排序
        获取第(step - 1) * 100 + 1到step * 100 + 1章的章节信息
        """
        offset = (step - 1) * 100 + 1
        cursor = self.conn.execute(
            "SELECT * FROM chapters WHERE book_id=? "
            "ORDER BY idx LIMIT 100 OFFSET ?", (book_id, offset)
        )
        chapter_list = []
        for row in cursor:
            chapter_list.append(ChapterInfo.from_api_dict(dict(row)))
        return chapter_list

    def update_chapter(self, book: Book) -> None:
        """更新章节的版本、标题或卷名"""
        book_id = book.info.book_id
        item_list = book.chapter_list

        with self.transaction():
            for ch in item_list:
                set_clause = (
                    f"book_id={book_id}," +
                    f"idx={item_list.index(ch) + 1}," +
                    f"item_id={ch.item_id}," +
                    f"version={ch.version}," +
                    f"title={ch.title}," +
                    f"volume_name={ch.volume_name}"
                )
                idx = item_list.index(ch) + 1
                self.conn.execute(
                f"UPDATE chapters SET {set_clause} WHERE book_id=? AND idx=?",
                    (book_id, idx)
                )

    # ---------- 正文操作 ----------
    def get_content(self, item_id: str) -> Optional[str]:
        """获取章节正文"""
        cursor = self.conn.execute("SELECT * FROM contents WHERE item_id=?", (item_id,))
        row = cursor.fetchone()
        return row['content'] if row else None

    def set_content(self, item_id: str, content: str) -> None:
        """存储或更新章节正文"""
        with self.transaction():
            self.conn.execute("""
                INSERT OR REPLACE INTO contents (item_id, content) VALUES (?, ?)
            """, (item_id, content))

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

    def add_custom_bookmark(self, book_id: str, bookmark_name: str, chapter_index: int) -> int:
        """
        添加自定义书签，自动分配一个非零的 bookmark_id（最小可用正整数）
        :return: 新书签的 bookmark_id
        """
        with self.transaction():
            # 找出当前 book_id 下最大的 bookmark_id（不包括 0）
            cursor = self.conn.execute(
                "SELECT MAX(bookmark_id) FROM bookmarks WHERE book_id=? AND bookmark_id!=0",
                (book_id,)
            )
            max_id = cursor.fetchone()[0] or 0
            new_id = max_id + 1
            self.conn.execute("""
                INSERT INTO bookmarks (book_id, bookmark_id, bookmark_name, chapter_index)
                VALUES (?, ?, ?, ?)
            """, (book_id, new_id, bookmark_name, chapter_index))
            return new_id

    def delete_custom_bookmark(self, book_id: str, bookmark_id: int) -> None:
        """删除自定义书签（bookmark_id 不能为 0）"""
        if bookmark_id == 0:
            raise ValueError("不能删除默认书签")
        with self.transaction():
            self.conn.execute(
                "DELETE FROM bookmarks WHERE book_id=? AND bookmark_id=?",
                (book_id, bookmark_id)
            )

    def get_all_bookmarks(self, book_id: str) -> List[Dict[str, Any]]:
        """获取某本书的所有书签（包含默认书签，默认书签排最前）"""
        cursor = self.conn.execute("""
            SELECT * FROM bookmarks WHERE book_id=?
            ORDER BY bookmark_id = 0 DESC, bookmark_id
        """, (book_id,))
        return [dict(row) for row in cursor.fetchall()]

    # ---------- 工作流程辅助方法（可选） ----------
    def ensure_chapter_content(self, book_id: str, idx: int, fetch_func=None) -> str:
        """
        确保指定章节的正文可用。
        如果正文不存在，则调用 fetch_func(item_id) 获取内容并存储。
        返回正文内容。
        """
        chapter = self.get_chapter(book_id, idx)
        if not chapter:
            raise ValueError(f"章节不存在: book_id={book_id}, idx={idx}")

        item_id = chapter['item_id']
        content = self.get_content(item_id)
        if content is None:
            if fetch_func is None:
                raise RuntimeError("正文不存在且未提供获取函数")
            content = fetch_func(item_id)
            self.set_content(item_id, content)
        return content