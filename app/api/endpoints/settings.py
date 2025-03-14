from fastapi import APIRouter, Depends, HTTPException, status, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.api.deps import get_current_user, get_current_admin_user
from app.core.config import settings, load_config
from app.models.database import User
from pathlib import Path
import yaml
import logging

# 设置日志
logger = logging.getLogger("api.settings")

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# 添加不带尾斜杠的路由，重定向到带斜杠的版本
@router.get("", response_class=HTMLResponse)
async def get_settings_page_no_slash(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """设置页面 - 无尾部斜杠版本"""
    return RedirectResponse(url="/api/settings/", status_code=status.HTTP_301_MOVED_PERMANENTLY)

@router.get("/", response_class=HTMLResponse)
async def get_settings_page(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """设置页面"""
    # 获取当前管理员用户
    admin_user, error = await get_current_admin_user(request, db)
    
    # 如果有错误，重定向到登录页面
    if error:
        if "管理员权限" in error:
            return RedirectResponse(url="/?error=需要管理员权限访问此页面")
        return RedirectResponse(url="/api/auth/login")
    
    return templates.TemplateResponse(
        "settings.html", 
        {
            "request": request,
            "settings": {
                "download": {
                    "qbittorrent_url": settings.download.qbittorrent_url,
                    "qbittorrent_port": settings.download.qbittorrent_port,
                    "qbittorrent_username": settings.download.qbittorrent_username,
                    "qbittorrent_password": settings.download.qbittorrent_password,
                    "download_dir": settings.download.download_dir
                },
                "hardlink": {
                    "enable": settings.hardlink.enable,
                    "output_base": settings.hardlink.output_base,
                },
                "tmdb_api": {
                    "enabled": settings.tmdb_api.enabled,
                    "api_key": settings.tmdb_api.api_key,
                },
                "llm": {
                    "enable": settings.llm.enable,
                    "url": settings.llm.url,
                    "token": settings.llm.token,
                    "model_name": settings.llm.model_name,
                }
            },
            "username": admin_user.username,
            "is_admin": admin_user.is_admin
        }
    )

@router.post("/update", response_class=HTMLResponse)
async def update_settings(
    request: Request,
    qbittorrent_url: str = Form(...),
    qbittorrent_port: int = Form(...),
    qbittorrent_username: str = Form(...),
    qbittorrent_password: str = Form(...),
    download_dir: str = Form(...),
    hardlink_enable: bool = Form(False),
    hardlink_output_base: str = Form(...),
    tmdb_enabled: bool = Form(False),
    tmdb_api_key: str = Form(""),
    llm_enable: bool = Form(False),
    llm_url: str = Form(...),
    llm_token: str = Form(...),
    llm_model_name: str = Form("gpt-3.5-turbo"),
    db: AsyncSession = Depends(get_db)
):
    """更新设置"""
    # 获取当前管理员用户
    admin_user, error = await get_current_admin_user(request, db)
    
    # 如果有错误，重定向到登录页面
    if error:
        if "管理员权限" in error:
            return RedirectResponse(url="/?error=需要管理员权限访问此页面")
        return RedirectResponse(url="/api/auth/login")
    
    try:
        # 读取现有配置
        config_path = Path("config/settings.yaml")
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        
        # 更新下载配置
        config["download"]["qbittorrent_url"] = qbittorrent_url
        config["download"]["qbittorrent_port"] = qbittorrent_port
        config["download"]["qbittorrent_username"] = qbittorrent_username
        config["download"]["qbittorrent_password"] = qbittorrent_password
        config["download"]["download_dir"] = download_dir
        
        # 更新硬链接配置
        config["hardlink"]["enable"] = hardlink_enable
        config["hardlink"]["output_base"] = hardlink_output_base
        
        # 更新TMDB API配置
        config["tmdb_api"]["enabled"] = tmdb_enabled
        config["tmdb_api"]["api_key"] = tmdb_api_key
        
        # 更新AI配置
        config["llm"]["enable"] = llm_enable
        config["llm"]["url"] = llm_url
        config["llm"]["token"] = llm_token
        config["llm"]["model_name"] = llm_model_name
        
        # 保存配置
        with open(config_path, "w") as f:
            yaml.safe_dump(config, f)

        # 重新载入settings
        settings = load_config()
        
        # 重定向回设置页面，带有成功消息
        return templates.TemplateResponse(
            "settings.html", 
            {
                "request": request,
                "settings": {
                    "download": {
                        "qbittorrent_url": qbittorrent_url,
                        "qbittorrent_port": qbittorrent_port,
                        "qbittorrent_username": qbittorrent_username,
                        "qbittorrent_password": qbittorrent_password,
                        "download_dir": download_dir
                    },
                    "hardlink": {
                        "enable": hardlink_enable,
                        "output_base": hardlink_output_base,
                    },
                    "tmdb_api": {
                        "enabled": tmdb_enabled,
                        "api_key": tmdb_api_key,
                    },
                    "llm": {
                        "enable": llm_enable,
                        "url": llm_url,
                        "token": llm_token,
                        "model_name": llm_model_name,
                    }
                },
                "username": admin_user.username,
                "is_admin": admin_user.is_admin,
                "success_message": "设置已成功更新"
            }
        )
        
    except Exception as e:
        logger.error(f"更新设置失败: {str(e)}")
        # 重定向回设置页面，带有错误消息
        return templates.TemplateResponse(
            "settings.html", 
            {
                "request": request,
                "settings": {
                    "download": {
                        "qbittorrent_url": qbittorrent_url,
                        "qbittorrent_port": qbittorrent_port,
                        "qbittorrent_username": qbittorrent_username,
                        "qbittorrent_password": qbittorrent_password,
                        "download_dir": download_dir
                    },
                    "hardlink": {
                        "enable": hardlink_enable,
                        "output_base": hardlink_output_base,
                    },
                    "tmdb_api": {
                        "enabled": tmdb_enabled,
                        "api_key": tmdb_api_key,
                    },
                    "llm": {
                        "enable": llm_enable,
                        "url": llm_url,
                        "token": llm_token,
                        "model_name": llm_model_name,
                    }
                },
                "username": admin_user.username,
                "is_admin": admin_user.is_admin,
                "error_message": f"设置更新失败: {str(e)}"
            }
        )
