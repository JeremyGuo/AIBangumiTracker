from typing import Optional, List, Dict
import qbittorrentapi
import os
from app.core.config import settings

class QBittorrentClient:
    def __init__(self):
        self.client = qbittorrentapi.Client(
            host=settings.download.qbittorrent_url,
            port=settings.download.qbittorrent_port,
            username=settings.download.qbittorrent_username,
            password=settings.download.qbittorrent_password,
        )
        # 尝试连接并验证
        try:
            self.client.auth_log_in()
        except qbittorrentapi.LoginFailed as e:
            raise Exception(f"qBittorrent登录失败: {str(e)} URL: {settings.download.qbittorrent_url}")
        except Exception as e:
            raise Exception(f"连接qBittorrent失败: {str(e)}")

    async def add_torrent(self, urls: List[str], save_path: Optional[str] = None) -> List[Dict]:
        """添加种子"""
        results = []
        for url in urls:
            try:
                torrent = self.client.torrents_add(
                    urls=[url],
                    save_path=save_path,
                    use_auto_torrent_management=False,
                )
                results.append({
                    "url": url,
                    "success": True,
                    "hash": torrent.hash if torrent else None
                })
            except Exception as e:
                results.append({
                    "url": url,
                    "success": False,
                    "error": str(e)
                })
        return results

    async def get_torrent_info(self, torrent_hash: str) -> Optional[Dict]:
        """获取种子信息"""
        try:
            torrent = self.client.torrents_info(torrent_hashes=[torrent_hash])[0]
            return {
                "hash": torrent.hash,
                "name": torrent.name,
                "size": torrent.size,
                "progress": torrent.progress,
                "state": torrent.state,
                "save_path": torrent.save_path,
                "content_path": torrent.content_path,
                "files": [
                    {
                        "name": f.name,
                        "size": f.size,
                        "progress": f.progress,
                        "priority": f.priority,
                        "is_seed": f.is_seed,
                        "path": os.path.join(torrent.content_path, f.name)
                    }
                    for f in torrent.files
                ]
            }
        except Exception:
            return None
    
    async def get_torrent_files(self, torrent_hash: str) -> List[Dict]:
        """获取种子文件列表"""
        try:
            torrent = self.client.torrents_info(torrent_hashes=[torrent_hash])[0]
            content_path = torrent.content_path
            
            return [
                {
                    "name": f.name,
                    "size": f.size,
                    "progress": f.progress,
                    "priority": f.priority,
                    "is_seed": f.is_seed,
                    "path": os.path.join(content_path, f.name)
                }
                for f in torrent.files
            ]
        except Exception:
            return []

    async def remove_torrent(self, torrent_hash: str, delete_files: bool = False) -> bool:
        """删除种子"""
        try:
            self.client.torrents_delete(
                delete_files=delete_files,
                torrent_hashes=[torrent_hash]
            )
            return True
        except Exception:
            return False

# 创建全局客户端实例
qbittorrent_client = QBittorrentClient()