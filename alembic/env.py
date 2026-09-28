"""Alembic migration environment.

Loads the database URL from application settings and the target metadata from
the ORM models so autogenerate has the full schema in view.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.db.base import Base

# Import model modules so their tables register on ``Base.metadata``.
from app.modules.auth import models as _auth_models  # noqa: F401
from app.modules.change import models as _change_models  # noqa: F401
from app.modules.dependency import models as _dependency_models  # noqa: F401
from app.modules.document import models as _document_models  # noqa: F401
from app.modules.meeting import models as _meeting_models  # noqa: F401
from app.modules.notification import models as _notification_models  # noqa: F401
from app.modules.report import models as _report_models  # noqa: F401
from app.modules.dashboard import models as _dashboard_models  # noqa: F401
from app.modules.copilot import models as _copilot_models  # noqa: F401
from app.modules.milestone import models as _milestone_models  # noqa: F401
from app.modules.finance import models as _finance_models  # noqa: F401
from app.modules.issue import models as _issue_models  # noqa: F401
from app.modules.organization import models as _org_models  # noqa: F401
from app.modules.portfolio import models as _portfolio_models  # noqa: F401
from app.modules.program import models as _program_models  # noqa: F401
from app.modules.project import models as _project_models  # noqa: F401
from app.modules.raid import models as _raid_models  # noqa: F401
from app.modules.risk import models as _risk_models  # noqa: F401
from app.modules.resource import models as _resource_models  # noqa: F401
from app.modules.sprint import models as _sprint_models  # noqa: F401
from app.modules.task import models as _task_models  # noqa: F401
from app.modules.timesheet import models as _timesheet_models  # noqa: F401
from app.modules.benefit import models as _benefit_models  # noqa: F401
from app.modules.skill import models as _skill_models  # noqa: F401
from app.modules.initiative import models as _initiative_models  # noqa: F401
from app.modules.workflow import models as _workflow_models  # noqa: F401
from app.modules.vendor import models as _vendor_models  # noqa: F401
from app.modules.integration import models as _integration_models  # noqa: F401
from app.modules.apikey import models as _apikey_models  # noqa: F401
from app.modules.aidelivery import models as _aidelivery_models  # noqa: F401
from app.modules.sso import models as _sso_models  # noqa: F401
from app.modules.jira import models as _jira_models  # noqa: F401
from app.modules.metrics import models as _metrics_models  # noqa: F401
from app.modules.projectkpi import models as _projectkpi_models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata


def _include_object(
    object_: object, name: str | None, type_: str, reflected: bool, compare_to: object
) -> bool:
    """Filter objects considered by autogenerate.

    The dev/test SQLite database intentionally omits the ``tasks.sprint_id``
    foreign key (SQLite cannot ``ALTER`` a table to add a constraint), so
    autogenerate would otherwise re-emit that foreign key into every new
    migration. Foreign keys on ``tasks`` are stable, so we exclude them from
    comparison to keep generated migrations clean. This affects autogenerate
    only, never the migrations that actually run.
    """
    if type_ == "foreign_key_constraint":
        table = getattr(object_, "table", None)
        if table is not None and table.name == "tasks":
            return False
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without a DBAPI)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode against a live connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=_include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
