from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.db.session import async_session
from app.models.database import Torrent
from app.core.config import settings
from app.services.qbittorrent import qbittorrent_client
from typing import Optional, List, Dict, Any
from app.models.database import File
from app.services.ai import ai_client
import os
import logging
import shutil
import pathlib

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
    
    async def get_torrent_files(self, db: AsyncSession, torrent_id: int) -> List[Dict[str, Any]]:
        """获取种子的文件列表"""
        result = await db.execute(
            select(File).where(File.torrent_id == torrent_id)
        )
        files = result.scalars().all()
        return [
            {
                "id": file.id,
                "name": file.name,
                "size": file.size,
                "path": file.path,
                "is_valid_episode": file.is_valid_episode,
                "extracted_episode": file.extracted_episode,
                "final_episode": file.final_episode
            }
            for file in files
        ]
    
    async def update_torrent_files(self, db: AsyncSession, torrent_id: int, torrent_info: dict):
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
            await db.commit()
            return

        # 获取文件列表
        files = torrent_info.get("files", [])
        if not files:
            logging.warning(f"种子 {torrent.hash} 文件列表为空")
            torrent.status = "failed"
            torrent.error_message = "种子文件列表为空"
            db.add(torrent)
            await db.commit()

            # 删除所有该种子的文件记录
            await db.execute(
                delete(File).where(File.torrent_id == torrent.id)
            )
            return
        
        # 删除之前的文件记录
        await db.execute(
            delete(File).where(File.torrent_id == torrent.id)
        )
        
        # 获取下载目录
        download_dir = settings.download.download_dir
        output_base = settings.hardlink.output_base
        enable_hardlink = settings.hardlink.enable
        
        # 获取Source信息
        from app.models.database import Source
        source_result = await db.execute(
            select(Source).where(Source.id == torrent.source_id)
        )
        source = source_result.scalar_one_or_none()
        if (not source):
            logging.warning(f"种子 {torrent.hash} 来源信息不存在")
        
        # 使用Source名称作为目录名
        source_name = source.title if source else "未知来源"
        target_dir = os.path.join(output_base, source_name)
        if source.media_type == "tv":
            # 如果是剧集，使用季度作为目录名
            target_dir = os.path.join(target_dir, f"Season {source.season}")
        
        # 确保目标目录存在
        if enable_hardlink:
            if not os.path.exists(target_dir):
                logging.info(f"硬链接目标目录: {target_dir}")
                os.makedirs(target_dir, exist_ok=True)
        
        # 获取种子名称用于路径处理
        torrent_name = torrent_info.get("name", "")
        
        for file_info in files:
            logging.info(f"处理文件: {file_info}")
            file_path = file_info.get("name", "")  # 相对于种子根目录的路径
            file_size = file_info.get("size", 0)
            
            if not file_path:
                continue
            
            # 构建完整路径
            full_path = os.path.join(download_dir, file_path)
            logging.info(f"处理文件: {full_path}")
            
            # 使用AI判断这个文件是否为需要保留的正片文件
            is_main_content = await ai_client.is_main_content(file_path)
            logging.info(f"文件 {file_path} 是否为主要内容: {is_main_content}")

            if not is_main_content:
                logging.info(f"文件 {file_path} 不是主要内容，跳过")
                continue

            # 使用AI提取剧集信息
            if source.use_ai_episode:
                episode_value = await ai_client.extract_episode(file_path)
            else:
                logging.warning(f"Source {source.id} 未启用AI提取剧集信息")
                continue
            if not episode_value:
                logging.warning(f"文件 {file_path} 未提取到剧集信息")
                continue
            logging.info(f"文件 {file_path} 提取的剧集信息: {episode_value}")
            
            # 创建文件记录
            file = File(
                torrent_id = torrent.id,
                name = file_path,
                size = file_size,
                path = full_path,
                is_valid_episode = episode_value is not None,
                extracted_episode = episode_value,
                final_episode = (episode_value + source.episode_offset) if episode_value is not None else None
            )
            db.add(file)
            await db.commit()

            try:
                await self.file_make_hardlink(db, file.id)
            except Exception as e:
                logging.warning(f"文件 {file_path} 硬链接失败: {str(e)}")
        logging.info(f"种子 {torrent.hash} 文件处理完成")

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

    async def refresh_torrent_files(self, db: AsyncSession, torrent_id: int) -> Optional[Torrent]:
        """刷新种子的文件列表"""
        result = await db.execute(
            select(Torrent).where(Torrent.id == torrent_id)
        )
        torrent = result.scalar_one_or_none()
        if not torrent:
            return None

        torrent_info = await qbittorrent_client.get_torrent_info(torrent.hash)
        if not torrent_info:
            torrent.status = "failed"
            torrent.error_message = "无法获取种子信息"
            db.add(torrent)
            await db.commit()
            return None

        await self.update_torrent_files(db, torrent_id, torrent_info)
        return torrent

    async def get_file_info(self, db: AsyncSession, file_id: int) -> Optional[Dict[str, Any]]:
        """获取文件信息"""
        from app.models.database import File
        result = await db.execute(
            select(File).where(File.id == file_id)
        )
        file = result.scalar_one_or_none()
        if not file:
            return None
        
        # 获取源信息
        from app.models.database import Torrent, Source
        torrent_result = await db.execute(
            select(Torrent).where(Torrent.id == file.torrent_id)
        )
        torrent = torrent_result.scalar_one_or_none()
        
        if not torrent:
            logging.error(f"文件 {file_id} 对应的种子不存在， 数据库损坏")
            raise Exception("数据库损坏")
        
        source_result = await db.execute(
            select(Source).where(Source.id == torrent.source_id)
        )
        source = source_result.scalar_one_or_none()
        
        return {
            "id": file.id,
            "name": file.name,
            "size": file.size,
            "path": file.path,
            "is_valid_episode": file.is_valid_episode,
            "extracted_episode": file.extracted_episode,
            "final_episode": file.final_episode,
            "source": {
                "id": source.id if source else None,
                "title": source.title if source else None,
                "season": source.season if source else None,
                "media_type": source.media_type if source else None,
            } if source else None
        }
    
    async def file_make_hardlink(self, db: AsyncSession, file_id: int) -> str:
        """为文件创建硬链接
        
        如果custom_path为None，则使用自动计算的路径
        返回创建的硬链接路径或错误信息
        """
        file_info = await self.get_file_info(db, file_id)
        if not file_info:
            return "文件不存在"
        
        source_path = file_info["path"]
        if not os.path.exists(source_path):
            return f"源文件不存在: {source_path}"
        
        # 检查是否开启硬链接
        if not settings.hardlink.enable:
            return "未开启硬链接功能"
        
        output_base = settings.hardlink.output_base
        if not output_base:
            return "未配置硬链接输出目录"
        
        # 自动计算目标路径
        if not file_info.get("source"):
            return "无法获取源信息，请指定目标路径"
        
        source = file_info["source"]
        source_title = source["title"]
        media_type = source["media_type"]
        
        # 获取文件扩展名
        _, file_ext = os.path.splitext(source_path)
        
        if media_type == "tv":
            # 对于电视剧
            season = source["season"]
            episode = file_info["final_episode"]
            
            if episode is None:
                return "无法获取剧集编号，请指定目标路径"
            
            # 创建目标路径: output_base/<source title>/<source season>/<source title> S<source season>E<final episode>
            season_dir = os.path.join(output_base, source_title, f"Season {season}")
            os.makedirs(season_dir, exist_ok=True)
            
            # 格式化季和集数
            season_str = str(season).zfill(2)
            episode_str = str(episode).zfill(2)
            
            # 生成文件名
            file_name = f"{source_title} S{season_str}E{episode_str}{file_ext}"
            dest_path = os.path.join(season_dir, file_name)
        else:
            # 对于电影
            # 创建目标路径: output_base/<source title>
            movie_dir = os.path.join(output_base, source_title)
            os.makedirs(movie_dir, exist_ok=True)
            
            # 使用原始文件名
            file_name = f"{source_title}{file_ext}"
            dest_path = os.path.join(movie_dir, file_name)
        
        # 确保目标目录存在
        dest_dir = os.path.dirname(dest_path)
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir, exist_ok=True)
        
        logging.info(f"创建硬链接: {source_path} -> {dest_path}")
        
        # 如果目标文件已存在，先删除
        if os.path.exists(dest_path):
            os.unlink(dest_path)
        
        try:
            # 创建硬链接
            os.link(source_path, dest_path)
            logging.info(f"创建硬链接成功: {source_path} -> {dest_path}")

            # 更新File表
            result = await db.execute(
                select(File).where(File.id == file_id)
            )
            file = result.scalar_one_or_none()
            if not file:
                return dest_path
            
            file.hardlink_path = dest_path
            file.hardlink_error = None
            file.hardlink_status = "success"
            db.add(file)
            await db.commit()
            
            return dest_path
        except Exception as e:
            logging.error(f"创建硬链接失败: {str(e)}")
            return f"创建硬链接失败: {str(e)}"

download_manager = DownloadManager()