from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.db.session import async_session
from app.models.database import Torrent
from app.core.config import settings
from app.services.qbittorrent import qbittorrent_client
from typing import Optional
from app.models.database import File

import logging

class DownloadManager:
    async def is_downloaded(self, hash: str) -> bool:
        """检查种子是否已经下载过"""
        async with async_session() as db:
            result = await db.execute(
                select(Torrent).where(Torrent.hash == hash)
            )
            return result.scalar_one_or_none() is not None

    async def create_download(
        self,
        source_id: int,
        title: str,
        url: str,
        hash: str
    ) -> Torrent:
        """创建新的下载任务"""
        async with async_session() as db:
            # 创建种子记录
            torrent = Torrent(
                hash=hash,
                source_id=source_id,
                url=url,
                status="downloading",
                download_progress=0.0,
                created_at=datetime.utcnow(),
                started_at=datetime.utcnow()
            )
            db.add(torrent)
            await db.commit()
            await db.refresh(torrent)

            try:
                # 添加到qBittorrent
                await qbittorrent_client.add_torrent(urls=[url])
            except Exception as e:
                # 如果添加失败，更新状态
                torrent.status = "failed"
                torrent.error_message = str(e)
                db.add(torrent)
                await db.commit()
                raise

            return torrent

    async def update_torrent_status(self, db: AsyncSession, torrent_id: int, torrent_info: dict):
        """更新种子状态"""
        result = await db.execute(
            select(Torrent).where(Torrent.id == torrent_id)
        )
        logging.info(f"更新种子状态: {torrent_id} {torrent_info}")
        torrent = result.scalar_one_or_none()
        if not torrent:
            return

        if not torrent_info:
            torrent.status = "failed"
            torrent.error_message = "无法获取种子信息"
        # 更新状态
        torrent.download_progress = torrent_info["progress"] * 100
        if torrent_info["state"] in ["uploading", "stalledUP", "forcedUP", "queuedUP", "pausedUP"]:
            if torrent.status != "downloaded":
                torrent.status = "downloaded"
                torrent.completed_at = datetime.utcnow()
                db.add(torrent)
                await db.commit()

                # 硬链接文件到指定目录，同时更新File表
                await self.update_torrent_files(db, torrent.id, torrent_info)
        else:
            if torrent_info["state"] in ["error", "missingFiles"]:
                torrent.status = "failed"
                torrent.error_message = f"qBittorrent状态: {torrent_info['state']}"
            else:
                # Downloading
                torrent.status = "downloading"
                torrent.error_message = None
            db.add(torrent)
            await db.commit()
    
    async def update_torrent_files(self, db: AsyncSession, torrent_id: int, torrent_info: Optional[dict]):
        """硬链接文件到指定目录"""
        result = await db.execute(
            select(Torrent).where(Torrent.id == torrent_id)
        )
        torrent = result.scalar_one_or_none()
        if not torrent:
            logging.warning(f"种子 {torrent_id} 不存在")
            return

        if not torrent_info:
            torrent_info = await qbittorrent_client.get_torrent_info(torrent.hash)
        if not torrent_info:
            logging.warning(f"种子 {torrent.hash} 信息获取失败")
            torrent.status = "failed"
            torrent.error_message = "无法获取种子信息"
            db.add(torrent)
            db.commit()
            return

        # 获取文件列表
        files = torrent_info["files"]
        if not files:
            logging.warning(f"种子 {torrent.hash} 文件列表为空")
            torrent.status = "failed"
            torrent.error_message = "种子文件列表为空"
            db.add(torrent)
            db.commit()

            # 删除所有该种子的文件记录
            await db.execute(
                delete(File).where(File.torrent_id == torrent.id)
            )
            return

    async def retry_download(self, db: AsyncSession, torrent_id: int) -> Optional[Torrent]:
        """重新开始下载失败的种子"""
        async with async_session() as db:
            # 获取种子信息
            result = await db.execute(
                select(Torrent).where(Torrent.id == torrent_id)
            )
            torrent = result.scalar_one_or_none()
            if not torrent:
                return None

            try:
                # 重置状态
                torrent.status = "downloading"
                torrent.download_progress = 0.0
                torrent.error_message = None
                torrent.started_at = datetime.utcnow()
                torrent.completed_at = None
                
                # 重新添加到qBittorrent
                await qbittorrent_client.add_torrent(urls=[torrent.url])
                
                db.add(torrent)
                await db.commit()
                await db.refresh(torrent)
                return torrent
                
            except Exception as e:
                torrent.status = "failed"
                torrent.error_message = f"重试下载失败: {str(e)}"
                db.add(torrent)
                await db.commit()
                return None
    
    async def get_downloading_torrents(self, db: AsyncSession):
        """获取所有下载中的种子"""
        result = await db.execute(
            select(Torrent).where(Torrent.status == "downloading")
        )
        return result.scalars().all()

    async def get_torrents_need_update(self, db: AsyncSession):
        """获取所有需要更新状态的种子"""
        result = await db.execute(
            select(Torrent).where(Torrent.status != "downloaded")
        )
        return result.scalars().all()

download_manager = DownloadManager()