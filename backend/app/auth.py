import hashlib
import re
import secrets
import unicodedata
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Request
from starlette.concurrency import run_in_threadpool

from .errors import BusinessError
from .repositories import utcnow

password_hasher = PasswordHasher()
# Verify nonexistent users with the same expensive operation as real users.
DUMMY_HASH = password_hasher.hash('not-an-account-password')


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def username_key(username):
    value = unicodedata.normalize('NFKC', username).strip()
    if not re.fullmatch(r'[\w.-]{3,32}', value):
        raise BusinessError('INVALID_USERNAME', '用户名为 3～32 个字母、数字、汉字、下划线、点或短横线')
    return value, value.casefold()


async def verify_password(password, encoded):
    try:
        return await run_in_threadpool(password_hasher.verify, encoded, password)
    except VerifyMismatchError:
        return False


async def create_session(request, response, user):
    settings = request.app.state.settings
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    now = utcnow()
    await request.app.state.db.sessions.insert_one({
        '_id': token_hash(token), 'user_id': user['_id'], 'csrf_token': csrf,
        'created_at': now, 'expires_at': now + timedelta(hours=settings.session_hours),
    })
    response.set_cookie(settings.cookie_name, token, httponly=True, secure=settings.production,
                        samesite='lax', max_age=settings.session_hours * 3600, path='/')
    return {'id': user['_id'], 'username': user['username'], 'csrf_token': csrf}


async def current_user(request: Request):
    settings = request.app.state.settings
    token = request.cookies.get(settings.cookie_name)
    session = None
    if token:
        session = await request.app.state.db.sessions.find_one({'_id': token_hash(token), 'expires_at': {'$gt': utcnow()}})
    if not session:
        raise BusinessError('LOGIN_REQUIRED', '请先登录', 401)
    user = await request.app.state.db.users.find_one({'_id': session['user_id']})
    if not user:
        raise BusinessError('LOGIN_REQUIRED', '登录已失效，请重新登录', 401)
    request.state.session = session
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        csrf = request.headers.get('X-CSRF-Token', '')
        if not secrets.compare_digest(csrf, session['csrf_token']):
            raise BusinessError('CSRF_FAILED', '页面凭证已失效，请刷新重试', 403)
    return user

