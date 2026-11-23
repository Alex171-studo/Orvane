from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from src.domain.models import Project, Work

if TYPE_CHECKING:
    from src.storage.session_repository import Archive


class Repository(Protocol):
    data: "Archive"

    def project(self, project_id: UUID) -> Project: ...
    def work(self, note_id: UUID) -> Work: ...
    def event(self, entity_id: UUID, kind: str, before: str | None, after: str | None): ...
