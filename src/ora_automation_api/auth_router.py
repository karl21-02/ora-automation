"""Google OAuth authentication router for desktop app."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

security = HTTPBearer(auto_error=False)


# =============================================================================
# Schemas
# =============================================================================


class GoogleTokenRequest(BaseModel):
    """Google OAuth authorization code exchange."""
    code: str
    redirect_uri: str = "urn:ietf:wg:oauth:2.0:oob"


class TokenResponse(BaseModel):
    """JWT token response."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class UserResponse(BaseModel):
    """User info response."""
    id: str
    email: str
    name: str
    picture: str | None


# =============================================================================
# JWT Helpers
# =============================================================================


def create_access_token(user_id: str) -> tuple[str, int]:
    """Create JWT access token."""
    expires_delta = timedelta(days=settings.jwt_expire_days)
    expire = datetime.now(timezone.utc) + expires_delta

    payload = {
        "sub": user_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }

    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, int(expires_delta.total_seconds())


def decode_token(token: str) -> str | None:
    """Decode and validate JWT token. Returns user_id or None."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        return payload.get("sub")
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# =============================================================================
# Dependencies
# =============================================================================


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Session = Depends(get_db),
) -> User:
    """Get current authenticated user from JWT token."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = decode_token(credentials.credentials)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.id == user_id).first()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def get_current_user_optional(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Session = Depends(get_db),
) -> User | None:
    """Get current user if authenticated, None otherwise."""
    if credentials is None:
        return None

    user_id = decode_token(credentials.credentials)
    if user_id is None:
        return None

    user = db.query(User).filter(User.id == user_id).first()

    if user is None or not user.is_active:
        return None

    return user


# =============================================================================
# Routes
# =============================================================================


@router.post("/google", response_model=TokenResponse)
def google_auth(
    request: GoogleTokenRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Exchange Google OAuth authorization code for JWT token.

    Desktop app flow:
    1. App opens Google OAuth in browser with redirect_uri = urn:ietf:wg:oauth:2.0:oob
    2. User authorizes and gets authorization code
    3. App sends code to this endpoint
    4. We exchange code for Google tokens
    5. We get user info from Google
    6. We create/update user in DB
    7. We return our JWT token
    """
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth not configured",
        )

    # Exchange authorization code for tokens (sync httpx)
    with httpx.Client() as client:
        token_response = client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": request.code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": request.redirect_uri,
                "grant_type": "authorization_code",
            },
        )

        if token_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to exchange code: {token_response.text}",
            )

        tokens = token_response.json()
        access_token = tokens.get("access_token")

        # Get user info from Google
        userinfo_response = client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        if userinfo_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to get user info from Google",
            )

        google_user = userinfo_response.json()

    google_id = google_user["id"]
    email = google_user["email"]
    name = google_user.get("name", email.split("@")[0])
    picture = google_user.get("picture")

    # Find or create user
    user = db.query(User).filter(User.google_id == google_id).first()

    now = datetime.now(timezone.utc)

    if user is None:
        # Create new user
        user = User(
            id=str(uuid.uuid4()),
            email=email,
            name=name,
            picture=picture,
            google_id=google_id,
            is_active=True,
            created_at=now,
            last_login_at=now,
        )
        db.add(user)
    else:
        # Update existing user
        user.email = email
        user.name = name
        user.picture = picture
        user.last_login_at = now

    db.commit()
    db.refresh(user)

    # Create JWT token
    token, expires_in = create_access_token(user.id)

    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
        user=UserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            picture=user.picture,
        ),
    )


@router.get("/me", response_model=UserResponse)
def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    """Get current user info."""
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        picture=current_user.picture,
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Refresh JWT token."""
    # Update last login
    current_user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    # Create new token
    token, expires_in = create_access_token(current_user.id)

    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
        user=UserResponse(
            id=current_user.id,
            email=current_user.email,
            name=current_user.name,
            picture=current_user.picture,
        ),
    )
