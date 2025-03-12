from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import async_session
from app.crud.source import source
from app.services.rss_parser import rss_parser
from app.services.download_manager import download_manager
from app.services.qbittorrent import qbittorrent_client

import logging

class Scheduler:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.is_checking = False
        self._setup_jobs()

    def _setup_jobs(self):
        """设置定时任务"""
        # 每分钟检查一次是否有需要更新的RSS源
        self.scheduler.add_job(
            self._check_rss_sources,
            IntervalTrigger(seconds=60),
            id='check_rss_sources',
            replace_existing=True
        )

    async def _check_rss_sources(self):
        """检查所有需要更新的RSS源"""
        if self.is_checking:
            return
        self.is_checking = True
        try:
            logging.info("开始检查RSS源")
            async with async_session() as db:
                # 获取所有活跃的RSS源
                sources = await source.get_active_rss_sources(db)
                
                for src in sources:
                    # 检查是否需要更新
                    if not src.last_check or \
                    (datetime.utcnow() - src.last_check).total_seconds() >= src.check_interval:
                        await self._process_rss_source(db, src)
            
            logging.info("开始更新下载中种子状态")
            async with async_session() as db:
                # 更新下载中的种子状态
                torrents = await download_manager.get_torrents_need_update(db)
                for torrent in torrents:
                    logging.info(f"检查种子 {torrent.hash} 状态")
                    info = await qbittorrent_client.get_torrent_info(torrent.hash)
                    await download_manager.update_torrent_status(db, torrent.id, info)
        finally:
            self.is_checking = False
        

    async def _process_rss_source(self, db: AsyncSession, src):
        """处理单个RSS源的更新"""
        try:
            # 解析RSS源
            feed_title, items = await rss_parser.parse_feed(src.url)
            if not items:
                return

            # 更新最后检查时间
            await source.update_last_check(db, db_obj=src)

            # 处理新的种子
            for item in items:
                # 检查是否已经下载过
                if not await download_manager.is_downloaded(item["hash"]):
                    # 创建新的下载任务
                    await download_manager.create_download(
                        source_id=src.id,
                        title=item["title"],
                        url=item["magnet"],  # 使用磁力链接
                        hash=item["hash"]
                    )
        except Exception as e:
            # 记录错误但不中断其他源的处理
            logging.warning(f"处理RSS源 {src.url} 时出错: {str(e)}")

    def start(self):
        """启动调度器"""
        self.scheduler.start()

    def shutdown(self):
        """关闭调度器"""
        self.scheduler.shutdown()
    
    async def manual_check(self):
        """手动触发一次RSS源检查"""
        logging.info("手动触发一次RSS源检查")
        self.scheduler.pause_job('check_rss_sources')
        await self._check_rss_sources()
        self.scheduler.resume_job('check_rss_sources')

scheduler = Scheduler() 