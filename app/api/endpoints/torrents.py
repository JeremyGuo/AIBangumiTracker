from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db, async_session
from app.api.deps import get_current_user, get_current_admin_user
from app.services.download_manager import download_manager
from app.models.database import User, Torrent
import logging

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger("api.torrents")

@router.get("/", response_class=HTMLResponse)
async def list_torrents_page(
    request: Request,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """种子列表页面"""
    user, error = await get_current_user(request, db)
    if error:
        return RedirectResponse(url="/api/auth/login", status_code=status.HTTP_303_SEE_OTHER)
            
    # 构建查询
    query = select(Torrent).order_by(Torrent.created_at.desc())
    
    # 根据状态过滤
    if status:
        query = query.where(Torrent.status == status)
    
    # 获取所有种子
    result = await db.execute(query)
    torrents = result.scalars().all()
    
    return templates.TemplateResponse(
        "torrent_list.html", 
        {
            "request": request,
            "torrents": torrents,
            "username": user.username,
            "is_admin": user.is_admin,
            "filter_status": status
        }
    )

@router.get("/list")
async def get_torrents(
    request: Request,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """获取种子列表API"""
    user, error = await get_current_user(request, db)
    if error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要身份验证"
        )
    
    # 构建查询
    query = select(Torrent).order_by(Torrent.created_at.desc())
    
    # 根据状态过滤
    if status:
        query = query.where(Torrent.status == status)
    
    # 获取所有种子
    result = await db.execute(query)
    torrents = result.scalars().all()
    
    return [
        {
            "id": torrent.id,
            "hash": torrent.hash,
            "source_id": torrent.source_id,
            "url": torrent.url,
            "status": torrent.status,
            "download_progress": torrent.download_progress,
            "error_message": torrent.error_message,
            "created_at": torrent.created_at,
            "started_at": torrent.started_at,
            "completed_at": torrent.completed_at
        }
        for torrent in torrents
    ]

@router.delete("/{torrent_id}")
async def delete_torrent(
    torrent_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """删除种子记录（仅管理员）"""
    # 查询种子是否存在
    result = await db.execute(select(Torrent).where(Torrent.id == torrent_id))
    torrent = result.scalar_one_or_none()
    
    if not torrent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="种子不存在"
        )
    
    # 删除种子记录
    await db.delete(torrent)
    await db.commit()
    
    logger.info(f"已删除种子 ID:{torrent_id}")
    return {"status": "success", "message": "种子已删除"}

@router.post("/{torrent_id}/retry")
async def retry_torrent_download(
    torrent_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """重新尝试下载失败的种子"""
    user, error = await get_current_user(request, db)
    if error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要身份验证"
        )
    
    # 检查种子是否存在
    result = await db.execute(select(Torrent).where(Torrent.id == torrent_id))
    torrent = result.scalar_one_or_none()
    
    if not torrent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="种子不存在"
        )
    
    # 重试下载
    updated_torrent = await download_manager.retry_download(db, torrent_id)
    
    if not updated_torrent:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="重试下载失败"
        )
    
    logger.info(f"已重新开始下载种子 ID:{torrent_id}")
    return {
        "status": "success", 
        "message": "已重新开始下载",
        "torrent": {
            "id": updated_torrent.id,
            "status": updated_torrent.status,
            "download_progress": updated_torrent.download_progress,
            "started_at": updated_torrent.started_at
        }
    }