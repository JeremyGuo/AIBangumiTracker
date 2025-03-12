from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request, Form
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from app.crud.user import authenticate_user, create_user, get_user_count, get_user_by_username
from app.schemas.user import Token, UserCreate, User
from app.db.session import get_db
from app.api.deps import get_current_user, get_current_admin_user
import logging

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger("api.auth")

# 添加登录页面的GET路由
@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """登录页面"""
    return templates.TemplateResponse(
        "login.html", 
        {"request": request}
    )

# 登录表单处理（网页表单提交）
@router.post("/login", response_class=HTMLResponse)
async def login_form(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    """处理登录表单"""
    user = await authenticate_user(db, username, password)
    if not user:
        return templates.TemplateResponse(
            "login.html", 
            {
                "request": request, 
                "error_message": "用户名或密码错误"
            }
        )
    
    # 创建访问令牌（使用用户ID）
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    logger.info(f"为用户 {user.username} (ID: {user.id}) 创建访问令牌")
    access_token = create_access_token(
        subject=user.id,  # 确保使用用户ID
        expires_delta=access_token_expires
    )
    
    # 创建带有Token的重定向响应
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/"
    )
    return response

# 添加注册页面的GET路由
@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, db: AsyncSession = Depends(get_db)):
    """注册页面"""
    # 检查是否是首次设置（没有用户）
    user_count = await get_user_count(db)
    is_first_user = user_count == 0
    
    return templates.TemplateResponse(
        "register.html", 
        {
            "request": request,
            "is_first_user": is_first_user
        }
    )

# 注册表单处理
@router.post("/register", response_class=HTMLResponse)
async def register_form(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    """处理注册表单"""
    try:
        # 检查是否是第一个用户
        user_count = await get_user_count(db)
        is_first_user = user_count == 0
        
        # 检查用户名是否已存在
        existing_user = await get_user_by_username(db, username)
        if existing_user:
            return templates.TemplateResponse(
                "register.html", 
                {
                    "request": request, 
                    "error_message": "用户名已存在",
                    "is_first_user": is_first_user
                }
            )
        
        # 创建新用户
        user_create = UserCreate(username=username, password=password)
        user = await create_user(db, user_create, is_admin=is_first_user)
        
        # 创建访问令牌并重定向到登录页面
        return RedirectResponse(url="/api/auth/login?registered=true", status_code=status.HTTP_303_SEE_OTHER)
        
    except Exception as e:
        logger.error(f"注册失败: {str(e)}")
        return templates.TemplateResponse(
            "register.html", 
            {
                "request": request, 
                "error_message": f"注册失败: {str(e)}",
                "is_first_user": is_first_user
            }
        )

# 添加登出路由
@router.get("/logout")
async def logout():
    """用户登出"""
    response = RedirectResponse(url="/api/auth/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="access_token", path="/")
    return response

# API登录端点（用于第三方客户端API调用）
@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """用户登录API（返回JWT令牌）"""
    user = await authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        subject=user.id,  # 确保使用用户ID
        expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

# 获取当前用户信息API
@router.get("/me", response_model=User)
async def read_users_me(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """获取当前用户信息"""
    user, error = await get_current_user(request, db)
    if error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error
        )
    return user

# 管理员创建用户API
@router.post("/create-admin", response_model=User)
async def create_admin_user(
    user: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """创建管理员用户（需要管理员权限）"""
    admin_user, error = await get_current_admin_user(request, db)
    if error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error
        )
    
    # 检查用户名是否已存在
    existing_user = await get_user_by_username(db, user.username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已存在"
        )
    
    return await create_user(db, user, is_admin=True)