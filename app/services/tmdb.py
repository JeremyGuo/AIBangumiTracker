from typing import Optional, Dict, List
import aiohttp
from app.core.config import settings

class TMDBClient:
    def __init__(self):
        self.api_key = settings.tmdb_api.api_key
        self.base_url = "https://api.themoviedb.org/3"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        if settings.general.http_proxy:
            self.proxy = settings.general.http_proxy[0]
        else:
            self.proxy = None

    async def _make_request(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        """发送请求到TMDB API"""
        if not settings.tmdb_api.enabled:
            return None
        
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}{endpoint}"
                params = params or {}
                params["api_key"] = self.api_key
                
                async with session.get(
                    url,
                    params=params,
                    proxy=self.proxy,
                    headers=self.headers
                ) as response:
                    if response.status != 200:
                        return None
                    return await response.json()
        except Exception:
            return None

    async def search_media(self, query: str) -> List[Dict]:
        """搜索媒体信息，返回可能的匹配列表"""
        results = []
        
        # 搜索电视剧
        tv_result = await self._make_request(
            "/search/tv",
            {"query": query, "language": "zh-CN"}
        )
        
        if tv_result and tv_result.get("results"):
            for show in tv_result["results"][:3]:  # 取前3个结果
                # 获取详细信息
                details = await self._make_request(f"/tv/{show['id']}")
                if details:
                    result = {
                        "id": show["id"],
                        "name": show["name"],
                        "original_name": show.get("original_name"),
                        "media_type": "tv",
                        "number_of_seasons": details.get("number_of_seasons", 0),
                        "seasons": [
                            {
                                "season_number": season["season_number"],
                                "episode_count": season["episode_count"],
                                "air_date": season.get("air_date")
                            }
                            for season in details.get("seasons", [])
                            if season["season_number"] > 0  # 跳过特别篇等
                        ]
                    }
                    results.append(result)

        # 搜索电影
        movie_result = await self._make_request(
            "/search/movie",
            {"query": query, "language": "zh-CN"}
        )
        
        if movie_result and movie_result.get("results"):
            for movie in movie_result["results"][:3]:  # 取前3个结果
                results.append({
                    "id": movie["id"],
                    "name": movie["title"],
                    "original_name": movie.get("original_title"),
                    "media_type": "movie"
                })

        return results

    async def get_season_episodes(self, show_id: int, season_number: int) -> Optional[Dict]:
        """获取指定季的详细剧集信息"""
        result = await self._make_request(
            f"/tv/{show_id}/season/{season_number}",
            {"language": "zh-CN"}
        )
        
        if result:
            return {
                "season_number": season_number,
                "episode_count": len(result.get("episodes", [])),
                "episodes": [
                    {
                        "episode_number": ep["episode_number"],
                        "name": ep.get("name"),
                        "air_date": ep.get("air_date")
                    }
                    for ep in result.get("episodes", [])
                ]
            }
        return None

# 创建全局TMDB客户端实例
tmdb_client = TMDBClient()