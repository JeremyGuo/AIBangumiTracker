from datetime import datetime, timedelta
from typing import Optional, Union, Any, Dict
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from app.core.config import settings
from app.schemas.token import TokenPayload
import logging

# 配置密码上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 配置 JWT
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7天

# 配置 OAuth2
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """获取密码哈希"""
    return pwd_context.hash(password)

def create_access_token(subject: Union[str, int], expires_delta: Optional[timedelta] = None) -> str:
    """
    创建访问令牌，始终使用用户ID（转换为字符串）作为subject
    
    Args:
        subject: 用户ID
        expires_delta: 过期时间增量
    """
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # 确保subject始终是字符串
    subject_str = str(subject)
    
    to_encode = {"exp": expire.timestamp(), "sub": subject_str}
    encoded_jwt = jwt.encode(to_encode, settings.general.secret_key, algorithm=ALGORITHM)
    return encoded_jwt

async def verify_token(token: str) -> Optional[TokenPayload]:
    """
    验证JWT令牌
    
    Args:
        token: JWT令牌
    
    Returns:
        TokenPayload对象或None（如果验证失败）
    """
    try:
        payload = jwt.decode(token, settings.general.secret_key, algorithms=[ALGORITHM])
        token_data = TokenPayload(**payload)
        
        # 检查是否过期
        if datetime.fromtimestamp(token_data.exp) < datetime.now():
            return None
            
        return token_data
    except (JWTError, Exception) as e:
        logging.error(f"JWT验证失败: {str(e)}")
        return None