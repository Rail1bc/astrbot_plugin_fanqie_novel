from dataclasses import dataclass, field
from typing import Optional, Any, Dict, List
import re

@dataclass
class BookInfo:

    book_id: str    # 书籍 ID
    book_name: str  # 书名
    alias_name: str # 别名
    original_book_name: str # 原书名
    author: str     # 作者
    abstract: str = ""  # 简介
    word_number: Optional[int] = None   # 字数
    serial_count: Optional[int] = None  # 章节数
    read_cnt_text: str = ""  # 在读人数
    score: Optional[float] = None   # 评分
    raw: Dict[str, Any] = field(default_factory=dict)   # 原始数据

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BookInfo":
        if data is None:
            raise ValueError("data is required")

        book_id = data.get("book_id")
        book_name = data.get("book_name")
        alias_name = data.get("alias_name") or data.get("book_flight_alias_name")
        original_book_name = data.get("original_book_name")
        author = data.get("author")
        abstract = data.get("abstract")
        word_number = data.get("word_number")
        serial_count = data.get("serial_count")
        read_cnt_text = data.get("read_cnt_text")
        score = data.get("score")

        return cls(
            book_id=book_id,
            book_name=book_name,
            alias_name=alias_name,
            original_book_name=original_book_name,
            author=author,
            abstract=abstract,
            word_number=word_number,
            serial_count=serial_count,
            read_cnt_text=read_cnt_text,
            score=score,
            raw=data,
        )
    @classmethod
    def from_dict_list(cls, data: List[dict]) -> List["BookInfo"]:
        return [BookInfo.from_dict(data) for data in data]

@dataclass
class ChapterInfo:
    item_id: str
    version: str
    title: str
    volume_name: str
    raw: Dict[str, Any] = field(default_factory=dict)   # 原始数据

    @classmethod
    def from_dict(cls, data: dict) -> "ChapterInfo":
        item_id = data.get("item_id")
        version = data.get("version")
        title = data.get("title")
        volume_name = data.get("volume_name")
        return cls(
            item_id=item_id,
            version=version,
            title=title,
            volume_name=volume_name,
            raw=data,
        )
    @classmethod
    def from_dict_list(cls, data: List[dict]) -> List["ChapterInfo"]:
        return [ChapterInfo.from_dict(data) for data in data]

@dataclass
class ContentInfo:
    item_id: str
    version: str
    title: str
    content: str
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api_dict(cls, chapter: ChapterInfo, data: dict,) -> "ContentInfo":
        title = data.get("title")
        content = data.get("content")
        return cls(
            item_id=chapter.item_id,
            version=chapter.version,
            title=title,
            content=ContentInfo.remove_tags(content),
            raw=data,
        )
    @classmethod
    def from_db_dict(cls, data: dict) -> "ContentInfo":
        item_id = data.get("item_id")
        version = data.get("version")
        title = data.get("title")
        content = ContentInfo.remove_tags(data.get("content"))
        suffix = "\\n 为保证服务质量，免费用户请不要下书！或前往网站赞助后刷新隐藏该提示(赞助用户一天可下载一万章)"
        if content.endswith(suffix):
            content = content[:-len(suffix)]
        content = content.replace("</p>", "\n")
        return cls(
            item_id=item_id,
            version=version,
            title=title,
            content=content,
            raw=data,
        )

    @classmethod
    def remove_tags(cls, content: str) -> str:
        # 去除所有HTML/XML标签
        text = re.sub(r'<[^>]+>', '', content)
        # 可选：清理多余的空白行（将多个连续换行合并为单个）
        text = re.sub(r'\n\s*\n', '\n', text)
        return text.strip()

    @classmethod
    def from_dict_list(cls, data: List[dict]) -> List["ContentInfo"]:
        return [ContentInfo.from_db_dict(data) for data in data]

    def to_str(self):
        return f"{self.title}\n{self.content}"
