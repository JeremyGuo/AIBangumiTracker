from typing import List, Dict, Optional, Tuple
import aiohttp
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from app.core.config import settings
import logging

class RSSParser:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        if settings.general.http_proxy:
            self.proxy = settings.general.http_proxy[0]
        else:
            self.proxy = None

    async def _fetch_content(self, url: str) -> Optional[str]:
        """获取内容"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=self.headers,
                    proxy=self.proxy,
                    timeout=30
                ) as response:
                    if response.status != 200:
                        return None
                    return await response.text()
        except Exception:
            return None

    async def _download_torrent(self, url: str) -> Optional[str]:
        """下载种子文件并提取磁力链接"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=self.headers,
                    proxy=self.proxy,
                    timeout=30
                ) as response:
                    if response.status != 200:
                        return None
                    content = await response.read()
                    # 解析种子文件
                    import bencodepy
                    torrent = bencodepy.decode(content)
                    info = torrent[b'info']
                    
                    # 生成 info_hash
                    import hashlib
                    info_hash = hashlib.sha1(bencodepy.encode(info)).hexdigest()
                    
                    # 构建基础磁力链接
                    magnet = f"magnet:?xt=urn:btih:{info_hash}"
                    
                    # 添加显示名称
                    if b'name' in info:
                        from urllib.parse import quote
                        name = info[b'name'].decode('utf-8', errors='ignore')
                        magnet += f"&dn={quote(name)}"
                    
                    # 添加 tracker
                    if b'announce' in torrent:
                        tracker = torrent[b'announce'].decode('utf-8', errors='ignore')
                        magnet += f"&tr={quote(tracker)}"
                    
                    # 添加备用 tracker 列表
                    if b'announce-list' in torrent:
                        for tracker in torrent[b'announce-list']:
                            if isinstance(tracker, list):
                                tracker = tracker[0]
                            tracker_str = tracker.decode('utf-8', errors='ignore')
                            magnet += f"&tr={quote(tracker_str)}"
                    
                    # 添加 DHT 节点
                    if b'nodes' in torrent:
                        for node in torrent[b'nodes']:
                            if isinstance(node, list) and len(node) >= 2:
                                host = node[0].decode('utf-8', errors='ignore')
                                port = str(node[1])
                                magnet += f"&dht={quote(host)}:{port}"
                    
                    return magnet
        except Exception:
            return None

    def _extract_magnet(self, content: str) -> Tuple[Optional[str], Optional[str]]:
        """从内容中提取磁力链接和哈希值"""
        # 匹配磁力链接以及其携带的信息 (dn, dht, tr, etc.)
        magnet_pattern = r'magnet:\?xt=urn:btih:([a-zA-Z0-9]+)(?:&dn=([^\s&]+))?(?:&tr=([^\s&]+))?(?:&dht=([^\s&]+))?.*'
        match = re.search(magnet_pattern, content)
        if match:
            return match.group(0), match.group(1)
        
        return None, None

    def _extract_torrent_url(self, content: str) -> Optional[str]:
        """提取种子文件链接"""
        # 匹配.torrent结尾的URL
        torrent_pattern = r'https?://[^\s<>"]+?\.torrent'
        match = re.search(torrent_pattern, content)
        if match:
            return match.group(0)
        return None

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """解析日期字符串"""
        try:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(date_str)
        except Exception:
            return None

    async def parse_feed(self, url: str) -> Tuple[Optional[str], List[Dict]]:
        """解析RSS源，返回(RSS标题, 条目列表)"""
        content = await self._fetch_content(url)
        if not content:
            return None, []

        try:
            # 解析XML
            root = ET.fromstring(content)
            
            # 提取RSS标题
            feed_title = None
            channel = root.find(".//channel")
            if channel is not None:
                title_elem = channel.find("title")
                if title_elem is not None and title_elem.text:
                    feed_title = title_elem.text.strip()
            
            # 查找所有项目
            items = root.findall(".//item")
            results = []
            
            for item in items:
                # 基本信息
                result = {
                    "title": None,
                    "link": None,
                    "published": None,
                    "magnet": None,
                    "hash": None
                }
                
                # 提取标题
                title_elem = item.find("title")
                if title_elem is not None and title_elem.text:
                    result["title"] = title_elem.text.strip()
                
                # 提取链接
                link_elem = item.find("link")
                if link_elem is not None and link_elem.text:
                    result["link"] = link_elem.text.strip()
                
                # 提取发布日期
                date_elem = item.find("pubDate")
                if date_elem is not None and date_elem.text:
                    result["published"] = self._parse_date(date_elem.text.strip())
                
                # 提取磁力链接或种子文件
                # 1. 从所有可能的字段中提取磁力链接
                for elem in item:
                    if elem.text:
                        magnet, hash_value = self._extract_magnet(elem.text)
                        if magnet:
                            logging.info(f"Magnet: {magnet}")
                            result["magnet"] = magnet
                            result["hash"] = hash_value
                            break
                
                # 2. 如果没有磁力链接，尝试下载种子文件
                if not result["magnet"]:
                    # convert item to text
                    item_text = ET.tostring(item, encoding='utf-8', method='xml').decode('utf-8')
                    torrent_url = self._extract_torrent_url(item_text)
                    if torrent_url:
                        magnet = await self._download_torrent(torrent_url)
                        if magnet:
                            result["magnet"] = magnet
                            # 从磁力链接中提取哈希值
                            hash_match = re.search(r'btih:([a-zA-Z0-9]+)', magnet)
                            if hash_match:
                                result["hash"] = hash_match.group(1)
                
                # 只添加有标题和磁力链接的条目
                if result["title"] and result["magnet"]:
                    results.append(result)
            
            return feed_title, results
        except Exception:
            return None, []

    async def validate_feed(self, url: str) -> bool:
        """验证RSS源是否有效"""
        content = await self._fetch_content(url)
        if not content:
            return False
            
        try:
            root = ET.fromstring(content)
            items = root.findall(".//item")
            return len(items) > 0
        except Exception:
            return False

    async def get_feed_basic_info(self, url: str) -> Optional[str]:
        """获取RSS基本信息，仅返回feed标题"""
        content = await self._fetch_content(url)
        if not content:
            return None

        try:
            # 解析XML
            root = ET.fromstring(content)
            
            # 提取RSS标题
            channel = root.find(".//channel")
            if channel is not None:
                title_elem = channel.find("title")
                if title_elem is not None and title_elem.text:
                    return title_elem.text.strip()
            return None
        except Exception:
            return None

# 创建全局RSS解析器实例
rss_parser = RSSParser()