from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from app.db.session import async_session
from app.models.database import Torrent, File, Source
from app.services.qbittorrent import qbittorrent_client
from app.services.ai import ai_client
from app.core.config import settings
import os
import aiofiles
import aiofiles.os
from datetime import datetime
import asyncio
from utils.file_handler import organize_file

router = APIRouter()

async def ask_ai_multiple(file_path: str, times: int = 3) -> bool:
    """
    多次请求AI判断文件是否为正片
    
    Args:
        file_path: 文件路径
        times: 请求次数
        
    Returns:
        bool: 是否应该保留
    """
    # 发起多次请求
    results = await asyncio.gather(
        *[ai_client.classify_file(file_path) for _ in range(times)],
        return_exceptions=True
    )
    
    # 过滤出成功的结果
    valid_results = [r for r in results if not isinstance(r, Exception)]
    
    # 如果没有任何成功的结果，返回False
    if not valid_results:
        return False
        
    # 统计保留票数（至少2票同意才保留）
    keep_votes = sum(1 for result in valid_results if result)
    return keep_votes >= 2

async def process_completed_torrent(hash: str):
    """处理下载完成的种子"""
    async with async_session() as db:
        # 获取种子信息
        result = await db.execute(
            select(Torrent).where(Torrent.hash == hash)
        )
        torrent = result.scalar_one_or_none()
        if not torrent:
            raise HTTPException(status_code=404, detail="Torrent not found")
        
        # 获取关联的Source信息
        source_result = await db.execute(
            select(Source).where(Source.id == torrent.source_id)
        )
        source = source_result.scalar_one_or_none()
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")
        
        # 获取qBittorrent中的文件列表
        torrent_files = await qbittorrent_client.get_torrent_files(hash)
        
        # 处理每个文件
        files_to_keep = []
        for file_info in torrent_files:
            # 使用AI判断文件是否为正片
            should_keep = await ask_ai_multiple(file_info["path"])
            
            # 如果是需要保留的文件，创建记录
            if should_keep:
                # 为文件创建硬链接
                success, hardlink_path, error = await organize_file(
                    file_path=file_info["path"],
                    source_name=source.title,
                    season=source.season
                )
                
                file = File(
                    torrent_id=torrent.id,
                    name=file_info["name"],
                    path=file_info["path"],
                    size=file_info["size"],
                    is_valid_episode=True,
                    created_at=datetime.utcnow(),
                    hardlink_path=hardlink_path,
                    hardlink_status="completed" if success else "failed",
                    hardlink_error=error
                )
                files_to_keep.append(file)
        
        # 添加需要保留的文件并更新种子状态
        for file in files_to_keep:
            db.add(file)
        
        # 更新种子状态
        torrent.status = "completed"
        torrent.completed_at = datetime.utcnow()
        db.add(torrent)
        
        await db.commit()

@router.get("/qbt/completed/{hash}")
async def handle_completed_torrent(hash: str):
    """处理qBittorrent完成通知"""
    await process_completed_torrent(hash)
    return {"status": "success"}