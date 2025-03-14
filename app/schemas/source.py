from typing import Optional, List, Dict
from pydantic import BaseModel
from datetime import datetime

# API请求模型
class AnalyzeSourceRequest(BaseModel):
    url: str
    type: str  # RSS/magnet

class CreateSourceRequest(BaseModel):
    url: str
    type: str  # RSS/magnet
    title: str
    media_type: str  # movie/tv
    season: Optional[int] = None
    episode_offset: int = 0
    episode_regex: Optional[str] = None
    use_ai_episode: bool = False
    enable_sr: bool = False
    check_interval: int = 3600

# TMDB相关模型
class TMDBResult(BaseModel):
    id: int
    title: str
    original_title: str
    type: str
    overview: Optional[str] = None
    first_air_date: Optional[str] = None
    release_date: Optional[str] = None
    seasons: Optional[List[dict]] = None

# Source响应模型
class SourceResponse(BaseModel):
    id: int
    url: str
    type: str
    title: str
    media_type: str
    season: Optional[int] = None
    episode_offset: int
    episode_regex: Optional[str] = None
    use_ai_episode: bool
    enable_sr: bool
    check_interval: int
    created_at: datetime
    last_check: Optional[datetime] = None

    class Config:
        from_attributes = True

# Source列表响应
class SourceList(BaseModel):
    total: int
    items: List[SourceResponse]

# Source分析响应
class AnalyzeSourceResponse(BaseModel):
    title: Optional[str] = None
    error: Optional[str] = None
    tmdb_results: Optional[List[Dict]] = None

# 基础Source模型
class SourceBase(BaseModel):
    url: str
    type: str
    title: str
    media_type: str
    season: Optional[int] = None
    episode_offset: int = 0
    use_ai_episode: bool = False
    enable_sr: Optional[bool] = False
    check_interval: int = 3600
    tmdb_id: str = ""

# Source创建过程中的响应模型
class SourceCreationResponse(BaseModel):
    step: str  # title_confirmation, season_selection, final_confirmation, completed
    title: Optional[str] = None
    error: Optional[str] = None
    seasons: Optional[list] = None
    source: Optional[dict] = None

# 更新Source时的请求模型
class SourceUpdate(BaseModel):
    title: Optional[str] = None
    season: Optional[int] = None
    episode_offset: Optional[int] = None
    episode_regex: Optional[str] = None
    use_ai_episode: Optional[bool] = None
    enable_sr: Optional[bool] = None
    check_interval: Optional[int] = None

# 数据库中的Source
class SourceInDB(SourceBase):
    id: int
    user_id: int
    created_at: datetime
    last_check: Optional[datetime] = None

    class Config:
        from_attributes = True

# API响应中的Source
class Source(SourceBase):
    id: int
    created_at: datetime
    last_check: Optional[datetime] = None

    class Config:
        from_attributes = True

# Source列表的响应
class SourceList(BaseModel):
    total: int
    items: list[Source]

# Source创建步骤的请求模型
class ConfirmTitle(BaseModel):
    title: str

class SelectSeason(BaseModel):
    season: int
    episode_offset: int = 0

class SourceWithTMDB(BaseModel):
    source: Source
    tmdb_results: List[TMDBResult]