import httpx

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import APIKeyCookie

from auth.auth import get_supabase_client


ACCESS_TOKEN_COOKIE = "paperpilot_access_token"

cookie_scheme = APIKeyCookie(
    name=ACCESS_TOKEN_COOKIE,
    auto_error=False,
)


def get_current_user(
    token: str | None = Depends(cookie_scheme),
    authorization: str | None = Header(default=None),
):
    # An explicit header takes precedence; never fall back to a cookie on failure.
    if authorization is not None:
        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise HTTPException(
                status_code=401,
                detail="Use Authorization: Bearer <access token>.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        token = parts[1]

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    try:
        client = get_supabase_client()

        response = client.auth.get_user(token)
        user = response.user

        if not user:
            raise ValueError("User not found.")

        return {
            "id": str(user.id),
            "email": user.email,
            "created_at": str(user.created_at),
            "access_token": token,
        }

    except Exception as error:
        if isinstance(error, (httpx.TimeoutException, httpx.NetworkError)) or str(getattr(error, 'status', '')) in {'500','502','503','504'} or 'retryable' in type(error).__name__.lower():
            raise HTTPException(status_code=503, detail="The sign-in service is temporarily unavailable. Your session has not been cleared. Try again shortly.") from error
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
        ) from error

