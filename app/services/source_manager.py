from typing import List, Dict, Optional, Tuple
from datetime import datetime
import re
from app.services.rss_parser import rss_parser
from app.services.tmdb import tmdb_client
from app.services.ai import ai_client
from app.models.database import Source
from app.crud.source import source as crud_source
from app.db.session import async_session
from app.schemas.source import SourceResponse
import logging

class SourceManager:
    async def _process_title(self, feed_title: str) -> Dict:
        """处理标题并搜索TMDB"""
        # 提取feed标题中的剧集名称
        logging.info(f"Received title: {feed_title}")
        cleaned_title = await ai_client.extract_name(feed_title)
        logging.info(f"Extracted title: {cleaned_title}")
        if (cleaned_title):
            tmdb_results = await tmdb_client.search_media(cleaned_title)
            return tmdb_results
        
        return {
            "error": "无法提取有效的剧集名称"
        }

    async def analyze_url(self, url: str, source_type: str) -> Dict:
        """分析URL，返回可能的媒体信息列表"""
        try:
            if source_type == "rss":
                # 只获取feed的基本信息而不是完整解析
                feed_title = await rss_parser.get_feed_basic_info(url)
                if not feed_title:
                    return {
                        "error": "无法从RSS获取标题"
                    }
                tmdb_results = await self._process_title(feed_title)
                return {
                    "title": feed_title,
                    "tmdb_results": tmdb_results
                }
                
            else:  # 磁力链接
                # TODO: 从磁力链接获取标题
                feed_title = None  # 这里应该是从某处获取的标题
                if not feed_title:
                    return {
                        "error": "无法从磁力链接获取标题"
                    }
                tmdb_results = await self._process_title(feed_title)
                return {
                    "title": feed_title,
                    "tmdb_results": tmdb_results
                }
            
        except Exception as e:
            return {
                "error": f"解析失败: {str(e)}"
            }

    async def create_source(
        self,
        user_id: int,
        url: str,
        source_type: str,
        name: str,
        tmdb_id: int,
        season: int,
        episode_offset: int = 0,
        episode_regex: Optional[str] = None,
        feed_title: Optional[str] = None,
        use_ai_episode: bool = False
    ) -> Dict:
        """创建新的Source"""
        try:
            async with async_session() as db:
                db_source = await crud_source.create_with_user(
                    db=db,
                    user_id=user_id,
                    obj_in={
                        "url": url,
                        "type": source_type,
                        "name": name,
                        "feed_title": feed_title,
                        "tmdb_id": tmdb_id,
                        "season": season,
                        "episode_offset": episode_offset,
                        "episode_regex": episode_regex,
                        "use_ai_episode": use_ai_episode
                    }
                )
                
                # 使用Pydantic模型确保返回格式一致
                return SourceResponse.model_validate(db_source).model_dump()
                
        except Exception as e:
            return {
                "error": f"创建Source失败: {str(e)}"
            }

# 创建全局Source管理器实例
source_manager = SourceManager()