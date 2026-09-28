"""Skills Matrix models.

A :class:`Skill` is an organisation-level catalogue entry; a
:class:`ResourceSkill` links a resource to a skill with a proficiency rating.
Together they form the skills matrix (resources x skills -> proficiency). This is
additive: the Resource module's freeform ``skills`` JSON list is left untouched.
"""

from __future__ import annotations

import enum
import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseEntity, TenantMixin
from app.db.enums import enum_column


class SkillCategory(enum.StrEnum):
    """The nature of a skill."""

    TECHNICAL = "technical"
    FUNCTIONAL = "functional"
    DOMAIN = "domain"
    LEADERSHIP = "leadership"
    OTHER = "other"


class Skill(BaseEntity, TenantMixin):
    """An organisation-level skill catalogue entry."""

    __tablename__ = "skills"

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    category: Mapped[SkillCategory] = mapped_column(
        enum_column(SkillCategory), default=SkillCategory.OTHER, index=True
    )
    description: Mapped[str] = mapped_column(String(2000), default="")


class ResourceSkill(BaseEntity, TenantMixin):
    """A resource's proficiency in a skill (a cell of the skills matrix)."""

    __tablename__ = "resource_skills"

    resource_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("resources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True
    )
    proficiency: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5
    years_experience: Mapped[Decimal | None] = mapped_column(Numeric(4, 1), nullable=True)
