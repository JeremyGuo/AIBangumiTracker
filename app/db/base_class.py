from typing import Any
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, mapped_column

class Base(DeclarativeBase):
    """
    SQLAlchemy 声明性基类
    所有数据库模型都应该继承这个类
    """
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # 根据类名自动生成表名
    @declared_attr.directive
    def __tablename__(cls) -> str:
        return cls.__name__.lower()

    # 用于序列化对象
    def dict(self) -> dict[str, Any]:
        return {
            column.name: getattr(self, column.name)
            for column in self.__table__.columns
        } 