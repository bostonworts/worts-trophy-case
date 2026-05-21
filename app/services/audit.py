from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AuditLog, Member


def record_audit(
    db: Session,
    *,
    actor: Member | None,
    action: str,
    entity_type: str,
    entity_id: int | None,
    summary: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_member_id=actor.id if actor is not None else None,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            summary=summary[:500],
            metadata_json=json.dumps(metadata, sort_keys=True) if metadata else None,
        )
    )
