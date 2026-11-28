from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

# Lowercased before storage, see models.User
Username = Annotated[
    str, StringConstraints(to_lower=True, pattern=r"^[A-Za-z0-9_-]{3,32}$")
]
# The upper bound keeps hashing cost predictable
Password = Annotated[str, StringConstraints(min_length=8, max_length=128)]


class Registration(BaseModel):
    username: Username
    password: Password


class Login(BaseModel):
    # No policy here: a policy change must not lock out existing accounts
    username: Annotated[str, StringConstraints(to_lower=True, max_length=32)]
    password: Annotated[str, StringConstraints(max_length=128)]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
