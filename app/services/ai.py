from typing import Optional, Dict, Tuple, List
import aiohttp
import json
import asyncio
from app.core.config import settings
from duckduckgo_search import DDGS
import logging

class AIClient:
    def __init__(self):
        self.url = settings.llm.url
        self.token = settings.llm.token
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        self.max_retries = 3
        self.retry_delay = 1  # 秒
        # Configure proxy for DuckDuckGo requests
        self.proxy = settings.general.http_proxy[0] if settings.general.http_proxy else None

    async def _make_request(self, prompt: str, max_retries: int = None) -> Optional[str]:
        """发送请求到AI服务"""
        if not settings.llm.enable:
            return None
            
        retries = max_retries or self.max_retries
        last_error = None
        
        for attempt in range(retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        settings.llm.url,
                        headers={
                            "Authorization": f"Bearer {settings.llm.token}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": settings.llm.model_name,
                            "messages": [
                                {"role": "system", "content": "你是一个专门用于分析动漫标题和剧集信息的AI助手。"},
                                {"role": "user", "content": prompt}
                            ],
                            "temperature": 0.1
                        }
                    ) as response:
                        if response.status != 200:
                            raise Exception(f"API返回状态码: {response.status}")
                        data = await response.json()
                        return data["choices"][0]["message"]["content"]
            except Exception as e:
                last_error = e
                if attempt < retries - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                continue
        
        return None

    async def _search_anime_info(self, keywords: List[str]) -> List[Dict[str, str]]:
        """使用DuckDuckGo搜索多个关键词的动漫信息"""
        all_results = []
        with DDGS(proxies={"http": self.proxy, "https": self.proxy} if self.proxy else None) as ddgs:
            for keyword in keywords:
                try:
                    # 对每个关键词进行搜索，限制在动漫相关网站
                    query = f"{keyword} 动漫"
                    logging.info(f"Searching for: {query}")
                    results = list(ddgs.text(query, max_results=3))
                    if results:
                        all_results.append({
                            "keyword": keyword,
                            "search_results": [
                                {
                                    "title": r["title"],
                                    "description": r["body"]
                                }
                                for r in results
                            ]
                        })
                except Exception:
                    continue
        return all_results

    async def extract_name(self, title: str) -> Optional[str]:
        """从标题中提取动漫名称"""
        # 对每个关键词进行搜索
        search_results = await self._search_anime_info([title])
        
        if not search_results:
            return None

        # 构建最终的提示，包含所有搜索结果
        final_prompt = f"""请根据以下信息确定动漫的标准名称。

<title>
{title}
</title>

上面是一个文件的名字，请帮助我分析这个文件的名字，提取出可能的动漫名称。

<search-data>"""
        for result in search_results:
            final_prompt += f"\n关键词 '{result['keyword']}' 的搜索结果:\n"
            for sr in result["search_results"]:
                final_prompt += f"- {sr['title']}\n  {sr['description']}\n"

        final_prompt += """</search-data>
文件名中，可能有作者、字幕组、动漫名、时间、第几级、季度等等。请帮助我找出文件名中，动漫的名字是哪部分。
文件名在 <title> 标签下，搜索文件名得到的结果在 <search-data> 标签下。
请先进行思考，然后再给出动漫的名字，动漫的名字用 <name> 标签输出。
"""

        for _ in range(2):  # 最多尝试两次
            response = await self._make_request(final_prompt)
            if not response:
                continue
            
            # Find name betwee <name> tags
            import re
            match = re.search(r"<name>(.*?)</name>", response, re.DOTALL)
            if not match:
                continue
                
            name = match.group(1).strip()
            if name.lower() == "null" or not name:
                continue
                
            return name
        return None

    async def extract_season(self, title: str) -> Optional[int]:
        """从标题中提取季度信息"""
        prompt = f"""请从这个标题中提取动漫的季度数字（如果有）。
只返回一个数字，例如：2
如果是第一季或找不到季度信息，返回null。
如果能找到多个可能的季度号，返回最可能的那个。

标题: {title}"""

        for _ in range(2):  # 最多尝试两次
            response = await self._make_request(prompt)
            if not response:
                continue
                
            try:
                if response.strip().lower() == "null":
                    continue
                season = int(response.strip())
                if 0 < season < 100:  # 合理的季度范围
                    return season
            except ValueError:
                continue
        return None

    async def extract_episode(self, title: str) -> Optional[int]:
        """从标题中提取集数信息"""
        prompt = f"""
<title>{title}</title>

请从标题中提取动漫的集数（如果有）。
将返回的集数填写在<episode>标签中。例如<episode>12</episode>。
如果找不到集数信息，返回null。
如果遇到类似OVA或特别篇，返回null。
标题放在<title>标签中，请在<title>标签中找到集数信息。
"""

        for _ in range(2):  # 最多尝试两次
            response = await self._make_request(prompt)
            if not response:
                continue
                
            try:
                import re
                match = re.search(r"<episode>(.*?)</episode>", response, re.DOTALL)
                if not match:
                    continue
                response = match.group(1)
                if response.strip().lower() == "null":
                    continue
                episode = int(response.strip())
                if 0 < episode < 1000:  # 合理的集数范围
                    return episode
            except ValueError:
                continue
        return None

    async def extract_media_type(self, title: str) -> Optional[str]:
        """判断是电影还是剧集"""
        prompt = f"""请判断这个动漫标题是电影还是剧集。
只返回"movie"或"tv"。
如果无法确定，返回null。

标题: {title}"""

        for _ in range(2):  # 最多尝试两次
            response = await self._make_request(prompt)
            if not response:
                continue
                
            media_type = response.strip().lower()
            if media_type in ["movie", "tv"]:
                return media_type
        return None

    async def extract_media_info(self, title: str) -> Dict:
        """从标题中提取媒体信息"""
        prompt = f"""请分析这个标题并提取以下信息（使用JSON格式回复）：
标题: {title}

需要提取的信息：
1. 动漫名称（去除字幕组、清晰度等信息）
2. 类型（movie或tv）
3. 如果是tv，提取季度数字（如果有）
4. 提取集数（如果有）

示例回复格式：
{{
    "name": "进击的巨人",
    "type": "tv",
    "season": 4,
    "episode": 28
}}

或者：
{{
    "name": "铃芽之旅",
    "type": "movie",
    "season": null,
    "episode": 1
}}"""

        response = await self._make_request(prompt)
        if not response:
            return {
                "name": None,
                "type": None,
                "season": None,
                "episode": None
            }
        
        try:
            # 这里需要解析返回的JSON字符串
            import json
            result = json.loads(response)
            return {
                "name": result.get("name"),
                "type": result.get("type"),
                "season": result.get("season"),
                "episode": result.get("episode")
            }
        except Exception:
            return {
                "name": None,
                "type": None,
                "season": None,
                "episode": None
            }

    async def is_main_content(self, file_path: str) -> bool:
        """
        判断文件是否为需要保留的正片或字幕文件
        
        Args:
            file_path: 文件的完整路径
            
        Returns:
            True如果是正片或正片字幕文件，否则False
        """
        prompt = f"""请分析这个文件路径，判断它是否是动漫的正片视频或者正片的字幕文件。
        
<path>{file_path}</path>

请回答"yes"或者"no"：
- "yes": 这个文件是主要内容（正片视频或字幕）
- "no": 这个文件是预告片、采访、花絮、样本、截图等非必要内容

<path>标签为要判断的文件名（包含目录），将判断的结果放到<result>标签中返回。

判断标准：
1. 如果文件扩展名是.mkv, .mp4, .avi, .ts等视频格式，并且文件名不包含"sample", "trailer", "preview"等词，那么很可能是正片
2. 如果文件扩展名是.ass, .srt, .ssa等字幕格式，并且文件名与正片视频相似，那么很可能是正片字幕
3. 扩展名为.nfo, .txt, .jpg, .png等非视频非字幕文件通常不是正片内容
4. 如果路径中包含"Samples", "Trailers", "Extras", "SP", 等文件夹，可能不是正片内容
5. 特典番外不算正片

请只回答"yes"或"no"。"""
        response = await self._make_request(prompt)
        import re
        match = re.search(r"<result>(.*?)</result>", response, re.DOTALL)
        if not match:
            return False
        if match.group(1).strip() == "yes":
            return True
        return False

# 创建全局AI客户端实例
ai_client = AIClient()