"""
JWT verification shared with auth_service via SECRET_KEY env var.
Also provides X-Internal-Token dep for service-to-service calls.
"""
import os
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from typing import Optional

SECRET_KEY = os.environ["SECRET_KEY"]
ALGORITHM = "HS256"
INTERNAL_SERVICE_TOKEN = os.environ.get("INTERNAL_SERVICE_TOKEN")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="http://localhost:8004/auth/login", auto_error=False)


class CurrentUser:
    def __init__(self, email: str, is_admin: bool = False):
        self.email = email
        self.is_admin = is_admin


async def get_current_user(token: Optional[str] = Depends(oauth2_scheme)) -> CurrentUser:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if not email:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        return CurrentUser(email=email, is_admin=bool(payload.get("is_admin", False)))
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


async def require_admin(current: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not current.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")
    return current


async def require_internal(x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token")):
    if not INTERNAL_SERVICE_TOKEN or x_internal_token != INTERNAL_SERVICE_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal token")
