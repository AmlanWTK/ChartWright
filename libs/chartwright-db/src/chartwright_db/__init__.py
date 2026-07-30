"""chartwright-db: persistence layer with RLS tenancy and audit-on-write (CP08)."""

from chartwright_db.models import (
    RLS_TABLES,
    AuditLog,
    Base,
    Document,
    DocumentPage,
    ExtractedField,
    ExtractedTable,
    Extraction,
    ReviewTask,
    Tenant,
    User,
)
from chartwright_db.repository import (
    DocumentRepository,
    ExtractionRepository,
    ReviewTaskRepository,
)
from chartwright_db.session import (
    admin_database_url,
    app_database_url,
    build_engine,
    no_tenant_session,
    tenant_context,
)

__all__ = [
    "RLS_TABLES",
    "AuditLog",
    "Base",
    "Document",
    "DocumentPage",
    "DocumentRepository",
    "ExtractedField",
    "ExtractedTable",
    "Extraction",
    "ExtractionRepository",
    "ReviewTask",
    "ReviewTaskRepository",
    "Tenant",
    "User",
    "admin_database_url",
    "app_database_url",
    "build_engine",
    "no_tenant_session",
    "tenant_context",
]

__version__ = "0.1.0"
