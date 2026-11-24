"""Centros de costos (D-060): código, nombre y archivo, un solo nivel.

Son una dimensión de gestión de las líneas de ingreso y gasto: no alteran los saldos
contables. La base impide un centro en una línea de otra cuenta o un centro archivado
(trigger de líneas). No se borran: se archivan.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.modules.accounting.common import apply_changes, flush_translated, now, record, snapshot
from app.modules.accounting.models import CostCenter

FIELDS = ("code", "name")


def get_center(
    db: Session, organization_id: uuid.UUID, center_id: uuid.UUID, *, lock: bool = False
) -> CostCenter:
    query = select(CostCenter).where(
        CostCenter.id == center_id, CostCenter.organization_id == organization_id
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    center = db.scalar(query)
    if center is None:
        raise NotFound("COST_CENTER_NOT_FOUND", "El centro de costos no existe.")
    return center


def list_centers(
    db: Session, organization_id: uuid.UUID, *, include_archived: bool = False
) -> list[CostCenter]:
    query = select(CostCenter).where(CostCenter.organization_id == organization_id)
    if not include_archived:
        query = query.where(CostCenter.archived_at.is_(None))
    return list(db.scalars(query.order_by(CostCenter.code)))


def create_center(
    db: Session, organization_id: uuid.UUID, actor_id: uuid.UUID, data: dict[str, Any]
) -> CostCenter:
    center = CostCenter(organization_id=organization_id, code=data["code"], name=data["name"])
    db.add(center)
    flush_translated(db)
    record(
        db,
        organization_id,
        actor_id,
        "cost_center",
        "created",
        center.id,
        after=snapshot(center, FIELDS),
    )
    db.commit()
    return center


def update_center(
    db: Session,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    center_id: uuid.UUID,
    data: dict[str, Any],
) -> CostCenter:
    center = get_center(db, organization_id, center_id, lock=True)
    changes: dict[str, Any] = {k: data[k] for k in FIELDS if data.get(k) is not None}
    if data.get("archived") is not None:
        archived = bool(data["archived"])
        if archived != (center.archived_at is not None):
            changes["archived_at"] = now() if archived else None
    before, after = apply_changes(center, changes)
    if after:
        flush_translated(db)
        record(
            db,
            organization_id,
            actor_id,
            "cost_center",
            "updated",
            center.id,
            before=before,
            after=after,
        )
    db.commit()
    return center
