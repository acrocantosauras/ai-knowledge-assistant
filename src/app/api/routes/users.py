"""User preferences API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db_session
from app.db.models.user import User
from app.schemas.preferences import (
    UserPreferences,
    UserPreferencesResponse,
    UserPreferencesUpdate,
    UserProfileResponse,
)
from app.services.auth import update_user_preferences

router = APIRouter(prefix="/users/me", tags=["users"])


@router.get(
    "/preferences", response_model=UserPreferences, status_code=status.HTTP_200_OK
)
async def get_user_preferences(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserPreferences:
    """Get current user's preferences."""
    return UserPreferences.model_validate(current_user.preferences or {})


@router.patch(
    "/preferences", response_model=UserPreferences, status_code=status.HTTP_200_OK
)
async def update_user_preferences_endpoint(
    data: UserPreferencesUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserPreferences:
    """Update current user's preferences."""
    # Merge existing preferences with updates
    existing_prefs = current_user.preferences or {}
    update_data = data.model_dump(exclude_unset=True, exclude_none=True)

    # Merge custom preferences
    if "custom" in update_data and update_data["custom"]:
        existing_custom = existing_prefs.get("custom", {})
        existing_custom.update(update_data.pop("custom"))
        update_data["custom"] = existing_custom

    merged_prefs = {**existing_prefs, **update_data}

    user = await update_user_preferences(db, current_user.id, merged_prefs)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return UserPreferences.model_validate(user.preferences or {})


@router.get(
    "/profile", response_model=UserProfileResponse, status_code=status.HTTP_200_OK
)
async def get_user_profile(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserProfileResponse:
    """Get current user's profile including preferences."""
    return UserProfileResponse(
        id=str(current_user.id),
        email=current_user.email,
        display_name=current_user.display_name,
        is_active=current_user.is_active,
        preferences=UserPreferencesResponse.model_validate(
            current_user.preferences or {}
        ),
    )
