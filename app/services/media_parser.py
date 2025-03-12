from typing import Optional, Dict, Tuple
import re
from app.services.ai import ai_client

class MediaParser:
    def __init__(self):
        pass

    async def extract_name(self, title: str, use_ai: bool = False) -> Optional[str]:
        """提取名称"""
        if use_ai:
            return await ai_client.extract_name(title)
        return None

    async def extract_season(
        self,
        title: str,
        use_ai: bool = False,
        manual_season: Optional[int] = None
    ) -> Dict[str, Optional[int]]:
        """提取季度信息"""
        result = {
            "extracted": None,
            "final": manual_season
        }
        
        # 如果有手动设置的季度，直接返回
        if manual_season is not None:
            return result
            
        # 使用AI提取
        if use_ai:
            result["extracted"] = await ai_client.extract_season(title)
            if result["extracted"] is not None:
                result["final"] = result["extracted"]
                return result
        return result

    async def extract_episode(
        self,
        title: str,
        use_ai: bool = False,
        episode_regex: Optional[str] = None,
        episode_offset: int = 0
    ) -> Dict[str, Optional[int]]:
        """提取集数信息"""
        result = {
            "extracted": None,
            "final": None
        }
        
        # 1. 使用AI提取
        if use_ai:
            result["extracted"] = await ai_client.extract_episode(title)
            if result["extracted"] is not None:
                result["final"] = result["extracted"] + episode_offset
                return result
        
        # 2. 使用提供的正则表达式
        if episode_regex:
            try:
                match = re.search(episode_regex, title)
                if match:
                    episode = int(match.group(1))
                    if 0 < episode < 1000:  # 合理的集数范围
                        result["extracted"] = episode
                        result["final"] = episode + episode_offset
                        return result
            except Exception:
                pass
        return result

    async def extract_media_type(self, title: str, use_ai: bool = False) -> Optional[str]:
        """提取媒体类型"""
        if use_ai:
            return await ai_client.extract_media_type(title)
        return None

# 创建全局解析器实例
media_parser = MediaParser() 