from typing import List, Tuple
from fastapi import APIRouter, Depends, HTTPException, status, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.session import get_db
from app.api.deps import get_current_user, get_current_admin_user
from app.crud.source import source
from app.services.source_manager import source_manager
from app.schemas.source import (
    SourceBase,
    Source,
    AnalyzeSourceRequest,
    AnalyzeSourceResponse
)
from app.models.database import User, Torrent, Source as SourceModel
from app.core.config import settings
import logging

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger("api.source")

@router.get("/{source_id}", response_class=HTMLResponse)
async def get_source_detail(
    request: Request,
    source_id: int,
    db: AsyncSession = Depends(get_db)
):
    """获取来源详细信息和相关种子"""
    # 验证用户登录
    user, error = await get_current_user(request, db)
    if error:
        return RedirectResponse(url="/api/auth/login", status_code=status.HTTP_303_SEE_OTHER)
    
    # 查询来源信息
    source_result = await db.execute(select(SourceModel).where(SourceModel.id == source_id))
    source = source_result.scalar_one_or_none()
    
    if not source:
        # 来源不存在，重定向到来源列表页面
        return RedirectResponse(
            url="/api/source?error=来源不存在", 
            status_code=status.HTTP_303_SEE_OTHER
        )
    
    # 查询该来源相关的所有种子，按创建时间降序排列
    torrent_result = await db.execute(
        select(Torrent)
        .where(Torrent.source_id == source_id)
        .order_by(Torrent.created_at.desc())
    )
    torrents = torrent_result.scalars().all()
    
    return templates.TemplateResponse(
        "source_detail.html", 
        {
            "request": request,
            "username": user.username,
            "is_admin": user.is_admin,
            "source": source,
            "torrents": torrents
        }
    )

@router.post("/analyze", response_model=AnalyzeSourceResponse)
async def analyze_source(
    request: AnalyzeSourceRequest,
    current_user: User = Depends(get_current_user)
):
    """分析来源URL，返回标题和TMDB匹配结果"""
    result = await source_manager.analyze_url(
        url=str(request.url),
        source_type=request.type
    )
    if "error" in result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
    return result

@router.get("/", response_class=HTMLResponse)
async def list_sources_page(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """源列表页面"""
    user, error = await get_current_user(request, db)
    if error:
        return RedirectResponse(url="/api/auth/login", status_code=status.HTTP_303_SEE_OTHER)
            
    # 获取所有来源
    sources = await source.get_multi_by_user(db, user_id=user.id)
    
    return templates.TemplateResponse(
        "source_list.html", 
        {
            "request": request,
            "sources": sources,
            "username": user.username,
            "is_admin": user.is_admin
        }
    )

@router.get("/create", response_class=HTMLResponse)
async def create_source_page(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """添加来源页面"""
    user, error = await get_current_user(request, db)
    if error:
        return RedirectResponse(url="/api/auth/login", status_code=status.HTTP_303_SEE_OTHER)
    
    return templates.TemplateResponse(
        "source_create.html", 
        {
            "request": request,
            "username": user.username,
            "is_admin": user.is_admin,
            "ai_enabled": settings.llm.enable,
            "sr_enabled": settings.enhancement.enable_sr,
            "tmdb_api_enabled": settings.tmdb_api.enabled
        }
    )

@router.post("/create", response_model=Source)
async def create_source(
    request: Request,
    source_in: SourceBase,
    db: AsyncSession = Depends(get_db)
):
    """创建新的来源"""
    user, error = await get_current_user(request, db)
    if error:
        return RedirectResponse(url="/api/auth/login", status_code=status.HTTP_303_SEE_OTHER)
    logging.info(f"创建新的来源: {source_in}")
    return await source.create_with_user(db, user_id=user.id, obj_in=source_in.model_dump())

@router.delete("/{source_id}")
async def delete_source(
    source_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """删除来源"""
    db_obj = await source.get_by_id(db, id=source_id)
    if not db_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="来源不存在"
        )
    
    await source.delete(db, id=source_id)
    return {"status": "success"}

@router.post("/{source_id}/reset-check", response_model=dict)
async def reset_source_check_time(
    source_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """重置来源的最后检查时间，强制下次检查RSS"""
    user, error = await get_current_user(request, db)
    if error:
        return RedirectResponse(url="/api/auth/login", status_code=status.HTTP_303_SEE_OTHER)
    
    db_obj = await source.get_by_id(db, id=source_id)
    if not db_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="来源不存在"
        )
    
    # 更新为很早的时间，确保下次检查会处理所有内容
    from datetime import datetime, timezone
    past_time = datetime(2000, 1, 1, tzinfo=timezone.utc)
    await source.update(db, db_obj=db_obj, obj_in={"last_check": past_time})
    
    logger.info(f"已重置来源 ID:{source_id} 的检查时间")
    return {"status": "success", "message": "已重置来源的检查时间"}