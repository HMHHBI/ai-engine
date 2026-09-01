from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import (
    generate_password_reset_token,
    hash_password,
    hash_reset_token,
    verify_reset_token,
)
from app.db.models import User, UserPlan
from app.utils.cloudinary_tool import upload_image_to_cloud


class UserRepository:
    # ============================================================
    # Lookup
    # ============================================================

    @staticmethod
    def get_by_email(
        db: Session,
        email: str,
    ) -> User | None:
        normalized_email = email.strip().lower()

        return db.execute(
            select(User).where(User.email == normalized_email)
        ).scalar_one_or_none()

    @staticmethod
    def get_by_id(
        db: Session,
        user_id: int,
    ) -> User | None:
        return db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()

    # ============================================================
    # User creation
    # ============================================================

    @staticmethod
    def create(
        db: Session,
        name: str,
        email: str,
        password: str,
        profile_image: str | None = None,
        plan: UserPlan = UserPlan.FREE,
    ) -> User:
        normalized_email = email.strip().lower()
        normalized_name = name.strip()

        if not normalized_name:
            raise ValueError("Name cannot be empty.")

        if not normalized_email:
            raise ValueError("Email cannot be empty.")

        if not isinstance(plan, UserPlan):
            try:
                plan = UserPlan(plan)
            except ValueError as exc:
                raise ValueError(f"Invalid user plan: {plan}") from exc

        existing_user = UserRepository.get_by_email(
            db,
            normalized_email,
        )

        if existing_user:
            raise ValueError("Email already registered.")

        new_user = User(
            name=normalized_name,
            email=normalized_email,
            password=hash_password(password),
            profile_image=profile_image,
            plan=plan,
        )

        db.add(new_user)

        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(new_user)

        return new_user

    # ============================================================
    # Profile
    # ============================================================

    @staticmethod
    def update_profile(
        db: Session,
        user_id: int,
        name: str | None = None,
        image_base64: str | None = None,
    ) -> User | None:
        user = UserRepository.get_by_id(
            db,
            user_id,
        )

        if not user:
            return None

        if name is not None:
            normalized_name = name.strip()

            if normalized_name:
                user.name = normalized_name

        if image_base64:
            cloud_url = upload_image_to_cloud(
                image_base64,
                folder="profiles",
            )

            if cloud_url:
                user.profile_image = cloud_url

        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(user)

        return user

    # ============================================================
    # Password reset
    # ============================================================

    @staticmethod
    def create_reset_token(
        db: Session,
        email: str,
        expires_minutes: int = 30,
    ) -> tuple[User | None, str | None]:
        """
        Generate a reset token and store ONLY its hash.

        Returns:
            (user, raw_token)

        The raw token must be sent to the user by email and must
        never be stored in the database.
        """

        if expires_minutes <= 0:
            raise ValueError("expires_minutes must be greater than zero.")

        user = UserRepository.get_by_email(
            db,
            email,
        )

        if not user:
            return None, None

        raw_token = generate_password_reset_token()

        user.reset_token_hash = hash_reset_token(raw_token)

        user.reset_token_expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=expires_minutes
        )

        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

        return user, raw_token

    @staticmethod
    def get_by_valid_reset_token(
        db: Session,
        raw_token: str,
    ) -> User | None:
        """
        Find the user associated with a reset token.

        Tokens are checked against their stored hash and expiration.
        """

        if not raw_token:
            return None

        token_hash = hash_reset_token(raw_token)

        user = db.execute(
            select(User).where(User.reset_token_hash == token_hash)
        ).scalar_one_or_none()

        if not user:
            return None

        expires_at = user.reset_token_expires_at

        if not expires_at:
            return None

        # PostgreSQL normally returns timezone-aware timestamps.
        # Normalize defensively if a naive datetime exists.
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if expires_at <= datetime.now(timezone.utc):
            return None

        # Constant-time verification adds defense in depth.
        if not verify_reset_token(
            raw_token,
            user.reset_token_hash,
        ):
            return None

        return user

    @staticmethod
    def consume_reset_token(
        db: Session,
        user: User,
        new_password: str,
    ) -> User:
        """
        Atomically consume a valid reset token and update the password.

        The token is invalidated in the same transaction as the
        password change.
        """

        if not new_password:
            raise ValueError("New password cannot be empty.")

        user.password = hash_password(new_password)

        user.reset_token_hash = None
        user.reset_token_expires_at = None

        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(user)

        return user

    # ============================================================
    # Plan
    # ============================================================

    @staticmethod
    def upgrade_to_pro(
        db: Session,
        user_id: int,
    ) -> User | None:
        user = UserRepository.get_by_id(
            db,
            user_id,
        )

        if not user:
            return None

        user.plan = UserPlan.PRO
        user.image_limit = 1000
        user.search_limit = 5000

        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(user)

        return user
