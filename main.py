import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from app.core.config import settings
from app.db.session import init_db, async_session
from app.api.endpoints import auth, source, webhook, settings as settings_endpoint, torrents
from app.services.scheduler import scheduler
from app.api.deps import get_current_user, get_token_from_request
from app.models.database import User
import logging

# 设置日志级别为INFO
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 初始化数据库
    logger.info("Initializing database")
    await init_db()
    
    # 启动调度器
    logger.info("Starting scheduler")
    scheduler.start()
    logger.info("Scheduler started")
    
    yield
    
    # 关闭调度器
    scheduler.shutdown()

app = FastAPI(
    title="AIAutoBangumi",
    description="自动视频下载分类系统",
    version="1.0.0",
    lifespan=lifespan
)

templates = Jinja2Templates(directory="app/templates")

# 静态文件目录
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# 注册路由
app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
app.include_router(source.router, prefix="/api/source", tags=["来源"])
app.include_router(webhook.router, prefix="/api/webhook", tags=["Webhook"])
app.include_router(settings_endpoint.router, prefix="/api/settings", tags=["设置"])
app.include_router(torrents.router, prefix="/api/torrents", tags=["种子"])

# 中间件处理认证问题
@app.middleware("http")
async def check_authentication(request: Request, call_next):
    # 公开路径列表
    public_paths = [
        "/api/auth/login", 
        "/api/auth/register",
        "/api/auth/token",
        "/static/",
        "/docs",
        "/redoc",
        "/openapi.json"
    ]
    
    # 检查是否是公开路径
    is_public = any(request.url.path.startswith(path) for path in public_paths)
    
    if not is_public:
        # 检查Token
        token = await get_token_from_request(request)
        if not token:
            # 如果是API请求，返回JSON错误
            if request.headers.get("accept") == "application/json" or \
               request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "未认证"}
                )
            # 否则重定向到登录页
            return RedirectResponse(url="/api/auth/login")
    
    response = await call_next(request)
    return response

# 添加前端友好的路由重定向
@app.get("/bangumis", response_class=HTMLResponse)
async def bangumis_redirect():
    """将 /bangumis 重定向到 /api/source"""
    return RedirectResponse(url="/api/source")

@app.get("/downloads", response_class=HTMLResponse)
async def downloads_page(request: Request):
    """下载管理页面 - 暂时重定向到首页，后续可实现专门的下载管理页面"""
    return RedirectResponse(url="/")

@app.get("/settings", response_class=HTMLResponse)
async def settings_redirect():
    """将 /settings 重定向到 /api/settings"""
    return RedirectResponse(url="/api/settings")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """首页"""
    # 获取用户总数和其他统计信息
    user_count = 0
    source_count = 0
    torrent_count = 0
    
    async with async_session() as db:
        from sqlalchemy import func, select
        from app.models.database import User, Source, Torrent
        
        result = await db.execute(select(func.count()).select_from(User))
        user_count = result.scalar_one()
        
        result = await db.execute(select(func.count()).select_from(Source))
        source_count = result.scalar_one()
        
        result = await db.execute(select(func.count()).select_from(Torrent))
        torrent_count = result.scalar_one()
        
        # 获取当前用户 - 处理新的返回格式
        current_user, error = await get_current_user(request, db)
    
    # 如果无法获取用户，继续显示页面但不包含用户信息
    username = current_user.username if current_user else None
    is_admin = current_user.is_admin if current_user else False
    
    return templates.TemplateResponse(
        "index.html", 
        {
            "request": request,
            "user_count": user_count,
            "source_count": source_count,
            "torrent_count": torrent_count,
            "username": username,
            "is_admin": is_admin,
            "error": error # 传递错误信息到模板
        }
    )

# 添加处理401错误的处理程序
@app.exception_handler(status.HTTP_401_UNAUTHORIZED)
async def unauthorized_exception_handler(request: Request, exc: HTTPException):
    """处理401未授权错误"""
    # 如果是API请求，返回JSON错误
    if request.headers.get("accept") == "application/json" or \
       request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": exc.detail}
        )
    # 否则重定向到登录页
    return RedirectResponse(url="/api/auth/login")

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.general.address[0],
        port=settings.general.listen,
        reload=True
    )