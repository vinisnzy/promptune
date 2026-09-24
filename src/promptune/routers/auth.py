from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from promptune.core.config import get_settings
from promptune.database.session import get_async_session
from promptune.dependencies.auth import AuthServiceDependency, CurrentUser
from promptune.repositories.user import UserRepository
from promptune.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    TokenPair,
    UserCreate,
    UserRead,
)
from promptune.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["Auth"])


def get_auth_service(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> AuthService:
    return AuthService(UserRepository(session), get_settings())


@router.post("/register", status_code=201, response_model=UserRead)
async def register(service: AuthServiceDependency, payload: UserCreate):
    return await service.register(payload)


@router.post("/login", response_model=TokenPair)
async def login(
    service: AuthServiceDependency,
    payload: Annotated[LoginRequest, Depends()],
):
    return await service.login(payload.email, payload.password)


@router.post("/refresh", response_model=TokenPair)
async def refresh(service: AuthServiceDependency, payload: RefreshRequest):
    return await service.refresh(payload.refresh_token)


@router.post("/logout", status_code=204)
async def logout(service: AuthServiceDependency, payload: RefreshRequest):
    await service.logout(payload.refresh_token)


@router.get("/me", response_model=UserRead)
async def me(current_user: CurrentUser):
    return current_user
