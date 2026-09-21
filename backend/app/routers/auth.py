"""Authentication and officer profile management routes.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Profile, generate_uuid
from app.schemas import OfficerSignup, OfficerLogin, ProfileOut, TokenResponse, RoleUpdate
from app.security import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_officer,
    require_admin,
)

router = APIRouter(prefix="/api/auth", tags=["Authentication & Profiles"])


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def officer_signup(data: OfficerSignup, db: Session = Depends(get_db)):
    """Register a new officer account. Default assigned role is INVESTIGATOR."""
    existing = db.query(Profile).filter(Profile.email == data.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An officer account with this email address already exists.",
        )

    officer_id = generate_uuid()
    new_profile = Profile(
        id=officer_id,
        email=data.email,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        badge_no=data.badge_no or "N/A",
        role="INVESTIGATOR",  # Enforced by default per PROJECT.md
        district=data.district or "Central",
    )
    db.add(new_profile)
    db.commit()
    db.refresh(new_profile)

    token = create_access_token(
        officer_id=new_profile.id,
        email=new_profile.email,
        role=new_profile.role,
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=86400,
        officer=ProfileOut.model_validate(new_profile),
    )


@router.post("/login", response_model=TokenResponse)
def officer_login(data: OfficerLogin, db: Session = Depends(get_db)):
    """Authenticate officer via email and password."""
    profile = db.query(Profile).filter(Profile.email == data.email).first()
    if not profile or not verify_password(data.password, profile.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials. Please verify your officer email and password.",
        )

    token = create_access_token(
        officer_id=profile.id,
        email=profile.email,
        role=profile.role,
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=86400,
        officer=ProfileOut.model_validate(profile),
    )


@router.get("/me", response_model=ProfileOut)
def get_my_profile(current_officer: Profile = Depends(get_current_officer)):
    """Retrieve the currently authenticated officer's profile."""
    return ProfileOut.model_validate(current_officer)


@router.post("/promote", response_model=ProfileOut)
def promote_officer_role(
    update: RoleUpdate,
    db: Session = Depends(get_db),
):
    """Promote an officer's role (INVESTIGATOR, SUPERVISOR, ADMIN).
    In production environments, strictly disabled via HTTP API to prevent privilege escalation.
    Authorized administrators must execute `python scripts/promote_officer.py` directly.
    """
    from app.config import settings
    if settings.ENVIRONMENT == "production":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Role promotion via public HTTP API is disabled in production. Use administrative CLI: python scripts/promote_officer.py",
        )

    if update.role not in ["INVESTIGATOR", "SUPERVISOR", "ADMIN"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role must be one of 'INVESTIGATOR', 'SUPERVISOR', 'ADMIN'",
        )

    profile = db.query(Profile).filter(Profile.email == update.email).first()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Officer with email '{update.email}' not found.",
        )

    profile.role = update.role
    db.commit()
    db.refresh(profile)
    return ProfileOut.model_validate(profile)
