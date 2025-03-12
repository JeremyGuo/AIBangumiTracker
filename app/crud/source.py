from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from app.models.database import Source
from app.schemas.source import SourceBase, SourceUpdate
from app.crud.base import CRUDBase
import logging

class CRUDSource(CRUDBase[Source, SourceBase, SourceUpdate]):
    async def create_with_user(
        self, db: AsyncSession, *, user_id: int, obj_in: Dict[str, Any]
    ) -> Source:
        """创建新的Source"""
        logging.info(f"创建新的Source: {obj_in}")
        db_obj = Source(
            type=obj_in["type"],
            url=obj_in["url"],
            media_type=obj_in["media_type"],
            title=obj_in["title"],
            season=obj_in.get("season"),
            use_ai_episode=obj_in.get("use_ai_episode", False),
            episode_regex=obj_in.get("episode_regex"),
            episode_offset=obj_in.get("episode_offset", 0),
            enable_sr=obj_in.get("enable_sr", False),
            check_interval=obj_in.get("check_interval", 3600)
        )
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def get_multi_by_user(
        self, db: AsyncSession, *, user_id: int = None, skip: int = 0, limit: int = 100
    ) -> List[Source]:
        """获取所有Source - 忽略user_id参数（临时修复）"""
        result = await db.execute(
            select(self.model)
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_id(self, db: AsyncSession, *, id: int) -> Optional[Source]:
        """通过ID获取Source"""
        result = await db.execute(
            select(self.model)
            .filter(Source.id == id)
        )
        return result.scalar_one_or_none()

    async def get_by_url(self, db: AsyncSession, *, url: str) -> Optional[Source]:
        """通过URL获取Source"""
        result = await db.execute(
            select(self.model)
            .filter(Source.url == url)
        )
        return result.scalar_one_or_none()

    async def update_last_check(
        self, db: AsyncSession, *, db_obj: Source
    ) -> Source:
        """更新最后检查时间"""
        from datetime import datetime
        db_obj.last_check = datetime.utcnow()
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def get_active_rss_sources(
        self, db: AsyncSession
    ) -> List[Source]:
        """获取所有需要检查的RSS源"""
        result = await db.execute(
            select(self.model)
            .where(Source.type == "RSS")
        )
        return list(result.scalars().all())

source = CRUDSource(Source)

async def get_source(db: AsyncSession, source_id: int) -> Optional[Source]:
    """获取单个来源"""
    result = await db.execute(
        select(Source).where(Source.id == source_id)
    )
    return result.scalar_one_or_none()

async def get_sources(db: AsyncSession) -> List[Source]:
    """获取所有来源"""
    result = await db.execute(select(Source))
    return list(result.scalars().all())

async def update_source(
    db: AsyncSession,
    source_id: int,
    source_update: SourceUpdate
) -> Optional[Source]:
    """更新来源"""
    update_data = source_update.model_dump(exclude_unset=True)
    if not update_data:
        return None
        
    await db.execute(
        update(Source)
        .where(Source.id == source_id)
        .values(**update_data)
    )
    await db.commit()
    
    return await get_source(db, source_id)

async def delete_source(db: AsyncSession, source_id: int) -> bool:
    """删除来源"""
    result = await db.execute(
        delete(Source).where(Source.id == source_id)
    )
    await db.commit()
    return result.rowcount > 0