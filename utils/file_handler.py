import os
from typing import Optional, Tuple
from app.core.config import settings
from app.services.media_parser import media_parser

async def extract_episode(filename: str) -> Optional[int]:
    """从文件名提取剧集号"""
    result = await media_parser.extract_episode(filename, use_ai=False)
    if result["final"] is not None:
        return result["final"]
    return None

def create_hardlink(source_path: str, target_path: str) -> Tuple[bool, Optional[str]]:
    """创建硬链接"""
    try:
        # 确保目标目录存在
        target_dir = os.path.dirname(target_path)
        os.makedirs(target_dir, exist_ok=True)
        
        # 创建硬链接
        os.link(source_path, target_path)
        return True, None
    except FileExistsError:
        # 如果文件已存在，视为成功
        return True, None
    except Exception as e:
        return False, str(e)

def format_episode_filename(source_name: str, season: Optional[int], episode: int, extension: str) -> str:
    """根据指定格式生成文件名"""
    if season is not None:
        # TV格式: <Source Name> S01E02.ext
        return f"{source_name} S{season:02d}E{episode:02d}{extension}"
    else:
        # 电影格式: <Source Name>.ext
        return f"{source_name}{extension}"

def get_target_path(source_file: str, source_name: str, season: Optional[int], episode: int) -> str:
    """获取目标文件路径"""
    # 获取基础输出目录和文件扩展名
    output_base = settings.hardlink.output_base
    _, extension = os.path.splitext(source_file)
    
    # 格式化文件名
    filename = format_episode_filename(source_name, season, episode, extension)
    
    if season is not None:
        # TV格式: <Output Base>/<Source Name>/S01/<Source Name> S01E02.ext
        season_dir = f"S{season:02d}"
        return os.path.join(output_base, source_name, season_dir, filename)
    else:
        # 电影格式: <Output Base>/<Source Name>/<Source Name>.ext
        return os.path.join(output_base, source_name, filename)

async def organize_file(file_path: str, source_name: str, season: Optional[int] = None) -> Tuple[bool, Optional[str], Optional[str]]:
    """组织文件（提取剧集、创建硬链接）"""
    # 从文件名提取剧集
    filename = os.path.basename(file_path)
    episode = await extract_episode(filename)
    
    if episode is None:
        return False, None, f"无法从文件名 '{filename}' 中提取剧集信息"
    
    # 获取目标文件路径
    target_path = get_target_path(file_path, source_name, season, episode)
    
    # 如果启用了硬链接，则创建硬链接
    if settings.hardlink.enable:
        success, error = create_hardlink(file_path, target_path)
        if not success:
            return False, None, f"创建硬链接失败: {error}"
        
        return True, target_path, None
    
    return True, target_path, None
