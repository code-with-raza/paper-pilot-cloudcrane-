"""Passwordless mobile sessions with per-request PKCE storage."""
import secrets
import threading
import time
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, EmailStr, Field
from auth.auth import get_supabase_client, format_user

router = APIRouter(prefix="/auth/mobile", tags=["Mobile authentication"])
_pending = {}
_pending_lock = threading.Lock()
LOGIN_TTL = 600
MAX_PENDING = 128

class EmailRequest(BaseModel):
    email: EmailStr

class LinkRequest(EmailRequest):
    create_account: bool = False

class VerifyRequest(EmailRequest):
    code: str = Field(pattern=r"^[0-9]{6,10}$")

class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=8192)

class ExchangeRequest(BaseModel):
    auth_code: str = Field(min_length=1, max_length=4096)
    login_request: str = Field(min_length=32, max_length=128)

class SessionResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict

def session_response(result, response):
    user = format_user(result.user, result.session)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return {
        "access_token": user["access_token"],
        "refresh_token": user["refresh_token"],
        "expires_in": result.session.expires_in,
        "user": {key: user[key] for key in ("id", "email", "created_at")},
    }

@router.post("/request-code")
def request_code(request: EmailRequest, response: Response):
    response.headers["Cache-Control"] = "no-store"
    try:
        get_supabase_client().auth.sign_in_with_otp({
            "email": str(request.email).strip().lower(),
            "options": {"should_create_user": False},
        })
    except Exception as error:
        if str(getattr(error, "status", "")) == "429":
            raise HTTPException(429, "Wait before requesting another code.") from error
    return {"message": "If this email has an account, a sign-in code will arrive shortly."}

@router.post("/verify-code", response_model=SessionResponse)
def verify_code(request: VerifyRequest, response: Response):
    try:
        result = get_supabase_client().auth.verify_otp({
            "email": str(request.email).strip().lower(),
            "token": request.code, "type": "email",
        })
        return session_response(result, response)
    except Exception as error:
        raise HTTPException(401, "Code is invalid or expired. Request a new code.") from error

@router.post("/refresh", response_model=SessionResponse)
def refresh(request: RefreshRequest, response: Response):
    try:
        result = get_supabase_client().auth.refresh_session(request.refresh_token)
        return session_response(result, response)
    except Exception as error:
        raise HTTPException(401, "Session expired. Sign in again.") from error

@router.post("/request-link")
def request_link(request: LinkRequest, response: Response):
    response.headers["Cache-Control"] = "no-store"
    client = get_supabase_client()
    email = str(request.email).strip().lower()
    ticket = secrets.token_urlsafe(32)
    now = time.monotonic()
    with _pending_lock:
        for key in list(_pending):
            if _pending[key]["expires"] <= now:
                del _pending[key]
        if len(_pending) >= MAX_PENDING:
            raise HTTPException(503, "Sign-in is busy. Try again shortly.")
        # The exact client retains the SDK-generated PKCE verifier.
        _pending[ticket] = {"client": client, "email": email,
                            "expires": now + LOGIN_TTL, "lock": threading.Lock()}
    try:
        client.auth.sign_in_with_otp({
            "email": email,
            "options": {
                "should_create_user": request.create_account,
                "email_redirect_to": "https://paperpilot-1obizdroqo.cloudcrane.ai/",
            },
        })
    except Exception as error:
        with _pending_lock:
            _pending.pop(ticket, None)
        status = str(getattr(error, "status", ""))
        code = str(getattr(error, "code", ""))
        if status == "429" or "rate_limit" in code:
            raise HTTPException(429, "Email sending limit reached. Wait before requesting another link.") from error
        if code in {"email_address_not_authorized", "email_address_invalid"}:
            raise HTTPException(403, "Email delivery is restricted. Contact the app owner or use your authorized email.") from error
        if code not in {"otp_disabled", "user_not_found", "signup_disabled"}:
            raise HTTPException(503, "Could not send a sign-in email. Please try again later.") from error
        # Keep account existence private. This ticket has no usable verifier/session.
    return {
        "message": "If email delivery is available, a sign-in link will arrive shortly.",
        "login_request": ticket,
        "expires_in": LOGIN_TTL,
    }

@router.post("/exchange-code", response_model=SessionResponse)
def exchange_code(request: ExchangeRequest, response: Response):
    response.headers["Cache-Control"] = "no-store"
    with _pending_lock:
        pending = _pending.get(request.login_request)
    if not pending or pending["expires"] <= time.monotonic():
        raise HTTPException(401, "This sign-in request expired. Request a fresh link.")
    if not pending["lock"].acquire(blocking=False):
        raise HTTPException(409, "Sign-in is already being completed. Please wait.")
    try:
        with _pending_lock:
            if _pending.get(request.login_request) is not pending:
                raise HTTPException(401, "This sign-in link has already been used.")
        result = pending["client"].auth.exchange_code_for_session({"auth_code": request.auth_code})
        if str(result.user.email or "").lower() != pending["email"]:
            raise ValueError("Sign-in account mismatch.")
        data = session_response(result, response)
        with _pending_lock:
            _pending.pop(request.login_request, None)
        return data
    except HTTPException:
        raise
    except Exception as error:
        with _pending_lock:
            _pending.pop(request.login_request, None)
        raise HTTPException(401, "Could not verify this link. Request a fresh sign-in email.") from error
    finally:
        pending["lock"].release()
