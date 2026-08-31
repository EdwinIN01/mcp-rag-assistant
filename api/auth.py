"""鉴权核心：用户存储（SQLite）+ JWT + API Key（阶段 5）。

设计要点：
- 双通道认证：Authorization: Bearer <jwt>（Web 前端登录态）
             X-API-Key: sk-mcprag-xxx（服务间调用 / MCP 客户端 / 脚本）
- 密码不存明文：PBKDF2-SHA256 + 随机盐，10 万次迭代
- API Key 不存明文：只存 SHA256 哈希，创建时一次性返回完整 Key；
  展示时仅暴露前缀（前 16 字符），支持吊销与最后使用时间追踪
- JWT：HS256 签名，sub=用户名，exp 控制有效期；未配置 JWT_SECRET 时
  每次启动随机生成（重启即全部失效，仅适合开发，日志会告警）
- AUTH_ENABLED=false：全量免认证（本地开发 / CI），业务代码无感知
- 认证结果（用户名）绑定到 structlog 上下文，与请求 ID 一起贯穿日志
"""
import datetime
import hashlib
import hmac
import secrets
import sqlite3
import threading
from dataclasses import dataclass

import jwt
import structlog
from fastapi import Depends, HTTPException, Request

from config import config

log = structlog.get_logger("auth")

_PBKDF2_ITERATIONS = 100_000


# ---------- 密码与 Key 的哈希工具 ----------

def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """PBKDF2-SHA256，返回 (hash_hex, salt_hex)。"""
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), _PBKDF2_ITERATIONS
    )
    return digest.hex(), salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    digest, _ = hash_password(password, salt)
    return hmac.compare_digest(digest, password_hash)


def _key_hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


# ---------- 用户 / API Key 存储 ----------

@dataclass
class AuthUser:
    """认证通过后的请求主体。"""
    username: str
    role: str
    via: str  # "jwt" / "api_key" / "disabled"


class UserStore:
    """SQLite 用户与 API Key 存储（线程安全，进程内单例）。"""

    def __init__(self, db_path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._create_tables()

    def _create_tables(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    username      TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    salt          TEXT NOT NULL,
                    role          TEXT NOT NULL DEFAULT 'user',
                    created_at    TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS api_keys (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    username     TEXT NOT NULL REFERENCES users(username),
                    name         TEXT NOT NULL,
                    key_hash     TEXT NOT NULL UNIQUE,
                    key_prefix   TEXT NOT NULL,
                    revoked      INTEGER NOT NULL DEFAULT 0,
                    created_at   TEXT NOT NULL,
                    last_used_at TEXT
                );
                """
            )
            self._conn.commit()

    @staticmethod
    def _now() -> str:
        return datetime.datetime.now().isoformat(timespec="seconds")

    # ---------- 用户 ----------
    def create_user(self, username: str, password: str, role: str = "user") -> None:
        password_hash, salt = hash_password(password)
        with self._lock:
            self._conn.execute(
                "INSERT INTO users (username, password_hash, salt, role, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (username, password_hash, salt, role, self._now()),
            )
            self._conn.commit()

    def get_user(self, username: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()
        return dict(row) if row else None

    def verify_user(self, username: str, password: str) -> dict | None:
        """校验用户名密码，通过返回用户记录，否则 None。"""
        user = self.get_user(username)
        if user is None:
            # 常数时间：避免用户不存在时提前返回造成时序差异
            verify_password(password, "0" * 64, "0" * 32)
            return None
        if verify_password(password, user["password_hash"], user["salt"]):
            return user
        return None

    def count_users(self) -> int:
        with self._lock:
            (n,) = self._conn.execute("SELECT COUNT(*) FROM users").fetchone()
        return n

    # ---------- API Key ----------
    def create_api_key(self, username: str, name: str) -> tuple[int, str]:
        """生成 API Key，返回 (key_id, 完整 key)。完整 key 仅此一次可见。"""
        key = config.api_key_prefix + secrets.token_hex(24)
        prefix = key[:16]
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO api_keys (username, name, key_hash, key_prefix, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (username, name, _key_hash(key), prefix, self._now()),
            )
            self._conn.commit()
            return cur.lastrowid, key

    def find_api_key(self, key: str) -> dict | None:
        """按完整 key 查找有效（未吊销）记录，并更新最后使用时间。"""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM api_keys WHERE key_hash = ? AND revoked = 0",
                (_key_hash(key),),
            ).fetchone()
            if row is None:
                return None
            self._conn.execute(
                "UPDATE api_keys SET last_used_at = ? WHERE id = ?",
                (self._now(), row["id"]),
            )
            self._conn.commit()
            return dict(row)

    def list_api_keys(self, username: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, name, key_prefix, revoked, created_at, last_used_at "
                "FROM api_keys WHERE username = ? ORDER BY id DESC",
                (username,),
            ).fetchall()
        return [dict(r) for r in rows]

    def revoke_api_key(self, username: str, key_id: int) -> bool:
        """吊销自己的 Key（越权吊销无效）。"""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE api_keys SET revoked = 1 WHERE id = ? AND username = ?",
                (key_id, username),
            )
            self._conn.commit()
        return cur.rowcount > 0

    def close(self) -> None:
        with self._lock:
            self._conn.close()


_store: UserStore | None = None
_store_lock = threading.Lock()


def get_store() -> UserStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = UserStore(config.auth_db_path)
    return _store


# ---------- JWT ----------

_jwt_secret: str | None = None


def _get_jwt_secret() -> str:
    """JWT 签名密钥：优先环境变量；未配置则进程内随机（重启失效，开发用）。"""
    global _jwt_secret
    if _jwt_secret is None:
        if config.jwt_secret:
            _jwt_secret = config.jwt_secret
        else:
            _jwt_secret = secrets.token_hex(32)
            log.warning(
                "jwt_secret_not_configured",
                hint="JWT_SECRET 未设置，已生成临时密钥（重启后所有 token 失效）",
            )
    return _jwt_secret


def issue_token(username: str) -> str:
    payload = {
        "sub": username,
        "iat": datetime.datetime.now(datetime.timezone.utc),
        "exp": datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(minutes=config.jwt_expire_minutes),
    }
    return jwt.encode(payload, _get_jwt_secret(), algorithm=config.jwt_algorithm)


def verify_token(token: str) -> str | None:
    """校验 JWT，通过返回用户名，失败返回 None。"""
    try:
        payload = jwt.decode(
            token, _get_jwt_secret(), algorithms=[config.jwt_algorithm]
        )
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


# ---------- FastAPI 认证依赖 ----------

_CREDENTIALS_ERROR = HTTPException(
    status_code=401,
    detail="未认证或凭证无效",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(request: Request) -> AuthUser:
    """业务接口统一认证依赖：JWT / API Key 双通道，AUTH_ENABLED=false 直通。"""
    if not config.auth_enabled:
        user = AuthUser(username="anonymous", role="admin", via="disabled")
        request.state.user = user
        return user

    # 通道 1：X-API-Key（服务间调用）
    api_key = request.headers.get("x-api-key")
    if api_key:
        record = get_store().find_api_key(api_key)
        if record is None:
            raise _CREDENTIALS_ERROR
        user_record = get_store().get_user(record["username"])
        if user_record is None:
            raise _CREDENTIALS_ERROR
        user = AuthUser(username=user_record["username"], role=user_record["role"], via="api_key")
        # 身份双写：state 供中间件日志（跨任务可见），contextvars 供业务日志
        request.state.user = user
        structlog.contextvars.bind_contextvars(user=user.username, auth_via="api_key")
        return user

    # 通道 2：Authorization: Bearer <jwt>
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        username = verify_token(token)
        if username is None:
            raise _CREDENTIALS_ERROR
        user_record = get_store().get_user(username)
        if user_record is None:  # 用户已删除但 token 未过期
            raise _CREDENTIALS_ERROR
        user = AuthUser(username=user_record["username"], role=user_record["role"], via="jwt")
        request.state.user = user
        structlog.contextvars.bind_contextvars(user=user.username, auth_via="jwt")
        return user

    raise _CREDENTIALS_ERROR
