from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import async_session
from app.models.database import Torrent
from app.core.config import settings
from app.services.qbittorrent import qbittorrent_client
from typing import Optional

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

    async def check_downloads(self):
        """检查所有下载中的种子状态"""
        try:
            # 获取qBittorrent中的所有种子状态
            torrents = await qbittorrent_client.get_torrents()
            
            async with async_session() as db:
                for torrent in torrents:
                    await self._update_torrent_status(db, torrent)
        except Exception as e:
            print(f"检查下载状态时出错: {str(e)}")

    async def _update_torrent_status(self, db: AsyncSession, torrent_info: dict):
        """更新种子状态"""
        result = await db.execute(
            select(Torrent).where(Torrent.hash == torrent_info["hash"])
        )
        torrent = result.scalar_one_or_none()
        if not torrent:
            return

        # 更新状态
        torrent.download_progress = torrent_info["progress"] * 100
        if torrent_info["state"] == "downloading":
            torrent.status = "downloading"
        elif torrent_info["state"] in ["uploading", "stalledUP"]:
            if torrent.status != "completed":
                torrent.status = "completed"
                torrent.completed_at = datetime.utcnow()
        elif torrent_info["state"] in ["error", "missingFiles"]:
            torrent.status = "failed"
            torrent.error_message = f"qBittorrent状态: {torrent_info['state']}"

        db.add(torrent)
        await db.commit()

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

download_manager = DownloadManager()