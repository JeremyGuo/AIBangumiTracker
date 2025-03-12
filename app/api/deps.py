from typing import Optional, Union, Tuple
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.core.security import verify_token, ALGORITHM
from app.core.config import settings
from jose import JWTError
from datetime import datetime
from app.schemas.token import TokenPayload
from app import crud
from app.models.database import User
import logging
from jose import jwt

# 设置日志
logger = logging.getLogger("api")

# 统一定义token处理
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

async def get_token_from_request(request: Request) -> Optional[str]:
    """
    按照统一顺序从请求中获取token:
    1. 首先从cookie中获取
    2. 然后从Authorization头获取
    3. 最后从请求参数中获取
    
    Args:
        request: 请求对象
    
    Returns:
        提取的token字符串或None
    """
    # 从cookie中获取
    token = request.cookies.get("access_token")
    if token and token.startswith("Bearer "):
        token = token.replace("Bearer ", "")
    
    # 从Authorization头获取
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.replace("Bearer ", "")
    
    # 从请求参数中获取
    if not token:
        token = request.query_params.get("token")
    
    return token

async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Tuple[Optional[User], Optional[str]]:
    """
    获取当前登录用户，不返回重定向对象，而是返回(User, None)或(None, error_message)
    
    Args:
        request: 请求对象
        db: 数据库会话
    
    Returns:
        元组 (User对象或None, 错误信息或None)
    """
    token = await get_token_from_request(request)
    
    if not token:
        return None, "未提供认证令牌"
    
    try:
        # 验证令牌
        payload = jwt.decode(
            token, settings.general.secret_key, algorithms=[ALGORITHM]
        )
        token_data = TokenPayload(**payload)
        
        # 检查令牌是否过期
        if datetime.fromtimestamp(token_data.exp) < datetime.now():
            logger.warning("令牌已过期")
            return None, "令牌已过期"
        
        # 获取用户ID - 安全地处理字符串类型的ID
        try:
            # token_data.sub 现在应该始终是字符串，但我们仍然需要将其转换为整数用于数据库查询
            user_id = int(token_data.sub)
            logger.info(f"从令牌中提取的用户ID: {user_id}")
        except (TypeError, ValueError) as e:
            logger.error(f"无法将用户ID转换为整数: {token_data.sub}, 错误: {str(e)}")
            return None, f"无效的用户ID格式: {token_data.sub}"
        
        # 获取用户
        user = await crud.user.get(db, id=user_id)
        if not user:
            logger.warning(f"找不到ID为 {user_id} 的用户")
            return None, f"找不到ID为 {user_id} 的用户"
        
        logger.info(f"成功获取用户: {user.username} (ID: {user.id})")
        return user, None
        
    except (JWTError, ValueError) as e:
        logger.error(f"令牌验证失败: {str(e)}")
        return None, f"令牌验证失败: {str(e)}"
    except Exception as e:
        logger.error(f"获取用户时发生未知错误: {str(e)}")
        return None, f"获取用户时发生未知错误: {str(e)}"

async def get_current_admin_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Tuple[Optional[User], Optional[str]]:
    """
    获取当前管理员用户，不返回重定向对象
    
    Args:
        request: 请求对象
        db: 数据库会话
    
    Returns:
        元组 (User对象或None, 错误信息或None)
    """
    user, error = await get_current_user(request, db)
    
    if error:
        return None, error
    
    if not user.is_admin:
        return None, "需要管理员权限访问此页面"
    
    return user, None