from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.database import User
from app.schemas.user import UserCreate
from app.core.security import get_password_hash, verify_password
from typing import Optional

async def get_user_by_username(db: AsyncSession, username: str):
    """通过用户名获取用户"""
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()

async def create_user(db: AsyncSession, user: UserCreate, is_admin: bool = False):
    """创建新用户"""
    db_user = User(
        username=user.username,
        hashed_password=get_password_hash(user.password),
        is_admin=is_admin
    )
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return db_user

async def authenticate_user(db: AsyncSession, username: str, password: str):
    """验证用户"""
    user = await get_user_by_username(db, username)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user

async def get_user_count(db: AsyncSession) -> int:
    """获取用户总数"""
    result = await db.execute(select(User))
    return len(result.all())

async def get(db: AsyncSession, id: int) -> Optional[User]:
    """通过ID获取用户"""
    result = await db.execute(select(User).where(User.id == id))
    return result.scalars().first()

# 保留此函数以避免现有代码影响，但内部使用更正的get函数
async def get_user_by_id(db: AsyncSession, user_id: int):
    """通过ID获取用户"""
    return await get(db, id=user_id)