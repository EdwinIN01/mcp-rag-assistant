"""认证接口：注册 / 登录（签发 JWT）/ 当前身份 / API Key 管理。"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from config import config
from ..auth import AuthUser, get_current_user, get_store, issue_token

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------- 请求/响应模型 ----------
class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32,
                          pattern=r"^[a-zA-Z0-9_-]+$",
                          description="用户名（字母数字下划线连字符）")
    password: str = Field(..., min_length=8, max_length=64, description="密码（至少 8 位）")


class TokenRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int


class UserInfoResponse(BaseModel):
    username: str
    role: str
    via: str = Field(description="认证通道：jwt / api_key / disabled")


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64, description="Key 用途备注")


class ApiKeyCreateResponse(BaseModel):
    key_id: int
    name: str
    key: str = Field(description="完整 API Key，仅创建时可见，请妥善保存")
    notice: str = "此 Key 仅展示一次，丢失请重新生成"


class ApiKeyInfo(BaseModel):
    id: int
    name: str
    key_prefix: str
    revoked: bool
    created_at: str
    last_used_at: str | None = None


class ApiKeyListResponse(BaseModel):
    keys: list[ApiKeyInfo]


class RevokeResponse(BaseModel):
    revoked: bool
    detail: str


# ---------- 认证接口 ----------
@router.post("/register", response_model=UserInfoResponse, status_code=201)
async def register(req: RegisterRequest):
    """注册新用户。首个注册用户自动成为 admin。"""
    store = get_store()
    if store.get_user(req.username):
        raise HTTPException(status_code=409, detail="用户名已存在")
    role = "admin" if store.count_users() == 0 else "user"
    store.create_user(req.username, req.password, role)
    return UserInfoResponse(username=req.username, role=role, via="register")


@router.post("/token", response_model=TokenResponse)
async def login(req: TokenRequest):
    """账号密码换取 JWT（Authorization: Bearer <token>）。"""
    user = get_store().verify_user(req.username, req.password)
    if user is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return TokenResponse(
        access_token=issue_token(req.username),
        expires_in_minutes=config.jwt_expire_minutes,
    )


@router.get("/me", response_model=UserInfoResponse)
async def me(user: AuthUser = Depends(get_current_user)):
    """当前认证身份（校验 JWT / API Key 是否有效）。"""
    return UserInfoResponse(username=user.username, role=user.role, via=user.via)


# ---------- API Key 管理 ----------
@router.post("/api-keys", response_model=ApiKeyCreateResponse, status_code=201)
async def create_api_key(
    req: ApiKeyCreateRequest, user: AuthUser = Depends(get_current_user)
):
    """为当前用户生成 API Key（完整 Key 仅返回一次，服务端只存哈希）。"""
    key_id, key = get_store().create_api_key(user.username, req.name)
    return ApiKeyCreateResponse(key_id=key_id, name=req.name, key=key)


@router.get("/api-keys", response_model=ApiKeyListResponse)
async def list_api_keys(user: AuthUser = Depends(get_current_user)):
    """列出当前用户的 API Key（仅前缀与元数据）。"""
    keys = [ApiKeyInfo(**k) for k in get_store().list_api_keys(user.username)]
    return ApiKeyListResponse(keys=keys)


@router.delete("/api-keys/{key_id}", response_model=RevokeResponse)
async def revoke_api_key(
    key_id: int, user: AuthUser = Depends(get_current_user)
):
    """吊销指定的 API Key（仅能吊销自己的）。"""
    ok = get_store().revoke_api_key(user.username, key_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Key 不存在或不属于当前用户")
    return RevokeResponse(revoked=True, detail=f"API Key #{key_id} 已吊销")
