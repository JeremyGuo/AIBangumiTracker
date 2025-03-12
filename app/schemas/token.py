from pydantic import BaseModel
from typing import Optional, Union
from datetime import datetime

class TokenPayload(BaseModel):
    """用于解析JWT令牌的payload数据"""
    sub: Optional[Union[int, str]] = None  # 支持整数或字符串格式的用户ID
    exp: Optional[float] = None
