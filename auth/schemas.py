
from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)

    @field_validator("password")
    @classmethod
    def strong_password(cls, value):
        if not (any(c.isupper() for c in value)
                and any(c.islower() for c in value)
                and any(c.isdigit() for c in value)
                and any(not c.isalnum() and not c.isspace() for c in value)):
            raise ValueError("Use at least 12 characters with uppercase, lowercase, a number and a special character.")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    created_at: str
