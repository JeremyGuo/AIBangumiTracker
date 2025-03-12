from datetime import datetime
from sqlalchemy import String, Boolean, ForeignKey, DateTime, Float, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base

class User(Base):
    username: Mapped[str] = mapped_column(String, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Source(Base):
    type: Mapped[str] = mapped_column(String)  # RSS/magnet
    url: Mapped[str] = mapped_column(String)
    media_type: Mapped[str] = mapped_column(String)  # movie/tv
    title: Mapped[str] = mapped_column(String, index=True)  # 媒体标题
    
    # 季度
    season: Mapped[int | None] = mapped_column(nullable=True)  # 季度（仅用于剧集）
    
    # 剧集提取方式
    use_ai_episode: Mapped[bool] = mapped_column(Boolean, default=False)  # 是否使用AI提取剧集
    episode_regex: Mapped[str | None] = mapped_column(String, nullable=True)  # 剧集正则表达式
    episode_offset: Mapped[int] = mapped_column(default=0)  # 剧集偏移量
    
    # 其他设置
    enable_sr: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_check: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # RSS最后检查时间
    check_interval: Mapped[int] = mapped_column(default=3600)  # RSS检查间隔（秒）
    
    # 关系
    torrents: Mapped[list["Torrent"]] = relationship(
        "Torrent",
        back_populates="source",
        cascade="all, delete-orphan",  # 当Source被删除时，删除所有关联的Torrent
        passive_deletes=True  # 启用数据库级别的级联删除
    )

class Torrent(Base):
    hash: Mapped[str] = mapped_column(String, unique=True, index=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("source.id", ondelete="CASCADE"),  # 当Source被删除时，删除关联的Torrent
        index=True
    )
    url: Mapped[str] = mapped_column(String)  # 磁力链接
    status: Mapped[str] = mapped_column(String)  # downloading/downloaded/failed
    download_progress: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)  # 错误信息
    
    # 关系
    source: Mapped["Source"] = relationship("Source", back_populates="torrents")
    files: Mapped[list["File"]] = relationship(
        "File",
        back_populates="torrent",
        cascade="all, delete-orphan",  # 当Torrent被删除时，删除所有关联的File
        passive_deletes=True  # 启用数据库级别的级联删除
    )

class File(Base):
    torrent_id: Mapped[int] = mapped_column(
        ForeignKey("torrent.id", ondelete="CASCADE"),  # 当Torrent被删除时，删除关联的File
        index=True
    )
    name: Mapped[str] = mapped_column(String)
    path: Mapped[str] = mapped_column(String)
    size: Mapped[int] = mapped_column()
    
    # 文件类型判断
    is_valid_episode: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # 是否为正片或其字幕文件
    ai_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)  # AI判断的置信度
    file_type: Mapped[str | None] = mapped_column(String, nullable=True)  # episode/subtitle/op/ed/sp/other
    
    # 剧集信息
    extracted_episode: Mapped[int | None] = mapped_column(nullable=True)  # 提取的剧集（AI或正则）
    final_episode: Mapped[int | None] = mapped_column(nullable=True)  # 最终使用的剧集（可能经过偏移）
    
    # 超分辨率相关
    sr_status: Mapped[str | None] = mapped_column(String, nullable=True)  # processing/completed/failed
    sr_progress: Mapped[float] = mapped_column(Float, default=0.0)
    sr_error: Mapped[str | None] = mapped_column(Text, nullable=True)  # 超分辨率错误信息
    
    # 硬链接相关
    hardlink_path: Mapped[str | None] = mapped_column(String, nullable=True)
    hardlink_status: Mapped[str | None] = mapped_column(String, nullable=True)  # pending/completed/failed
    hardlink_error: Mapped[str | None] = mapped_column(Text, nullable=True)  # 硬链接错误信息
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # 处理完成时间
    
    # 关系
    torrent: Mapped["Torrent"] = relationship("Torrent", back_populates="files")