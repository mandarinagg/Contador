"""D-025 / BR-FIN-05: la **base** impide mezclar contextos y monedas.

Estas pruebas insertan directamente con SQL, sin pasar por el servicio: demuestran que
ni un error de código podría guardar un movimiento personal con una cuenta empresarial.
"""

from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.conftest import auth_header
from tests.finance_utils import (
    API,
    business_context,
    create_account,
    ok,
    personal_context,
)

INSERT_TX = text(
    """
    INSERT INTO finance.transactions (context_id, account_id, currency, booked_on, amount,
        description, category_id, counterparty_id, source, dedupe_key, created_by,
        transfer_group_id, voided_at, voided_by, void_reason)
    VALUES (:context_id, :account_id, :currency, DATE '2026-03-01', :amount, 'SQL directo',
        :category_id, :counterparty_id, 'manual', sha256('x'::bytea), :user_id,
        :transfer_group_id, :voided_at, :voided_by, :void_reason)
    """
)


@pytest.fixture
def setup(client: TestClient, owner_token: str, db: Session) -> dict[str, Any]:
    biz = business_context(client, owner_token)
    per = personal_context(client, owner_token)
    biz_account = create_account(client, owner_token, biz, "Cuenta empresa", currency="PYG")
    per_account = create_account(client, owner_token, per, "Cuenta personal", currency="PYG")
    per_category = ok(
        client.post(
            f"{API}/contexts/{per}/categories",
            json={"name": "Supermercado", "kind": "expense"},
            headers=auth_header(owner_token),
        ),
        201,
    )
    biz_category = ok(
        client.post(
            f"{API}/contexts/{biz}/categories",
            json={"name": "Ventas", "kind": "income"},
            headers=auth_header(owner_token),
        ),
        201,
    )
    biz_counterparty = ok(
        client.post(
            f"{API}/contexts/{biz}/counterparties",
            json={"name": "Cliente SA", "kind": "customer"},
            headers=auth_header(owner_token),
        ),
        201,
    )
    user_id = db.scalar(text("SELECT id FROM core.users WHERE email = 'owner@example.com'"))
    return {
        "biz": biz,
        "per": per,
        "biz_account": biz_account["id"],
        "per_account": per_account["id"],
        "per_category": per_category["id"],
        "biz_category": biz_category["id"],
        "biz_counterparty": biz_counterparty["id"],
        "user_id": user_id,
    }


def _params(s: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    params = {
        "context_id": s["per"],
        "account_id": s["per_account"],
        "currency": "PYG",
        "amount": -1000,
        "category_id": None,
        "counterparty_id": None,
        "user_id": s["user_id"],
        "transfer_group_id": None,
        "voided_at": None,
        "voided_by": None,
        "void_reason": None,
    }
    params.update(overrides)
    return params


def _rejected(db: Session, params: dict[str, Any], constraint: str) -> None:
    nested = db.begin_nested()
    with pytest.raises(IntegrityError, match=constraint):
        db.execute(INSERT_TX, params)
    nested.rollback()


def test_valid_insert_is_accepted(db: Session, setup: dict[str, Any]) -> None:
    db.execute(INSERT_TX, _params(setup, category_id=setup["per_category"]))


def test_personal_transaction_cannot_use_business_account(
    db: Session, setup: dict[str, Any]
) -> None:
    _rejected(
        db,
        _params(setup, account_id=setup["biz_account"]),
        "fk_transactions_account_id_accounts",
    )


def test_transaction_cannot_use_category_or_counterparty_of_other_context(
    db: Session, setup: dict[str, Any]
) -> None:
    _rejected(
        db,
        _params(setup, category_id=setup["biz_category"]),
        "fk_transactions_category_id_categories",
    )
    _rejected(
        db,
        _params(setup, counterparty_id=setup["biz_counterparty"]),
        "fk_transactions_counterparty_id_counterparties",
    )


def test_transaction_currency_must_match_account(db: Session, setup: dict[str, Any]) -> None:
    _rejected(db, _params(setup, currency="USD"), "fk_transactions_account_id_accounts")


def test_account_currency_cannot_change_under_its_transactions(
    db: Session, setup: dict[str, Any]
) -> None:
    db.execute(INSERT_TX, _params(setup))
    nested = db.begin_nested()
    with pytest.raises(IntegrityError, match="fk_transactions_account_id_accounts"):
        db.execute(
            text("UPDATE finance.accounts SET currency = 'USD' WHERE id = :id"),
            {"id": setup["per_account"]},
        )
    nested.rollback()


def test_other_invariants_in_database(db: Session, setup: dict[str, Any]) -> None:
    _rejected(db, _params(setup, amount=0), "ck_transactions_amount_not_zero")
    _rejected(db, _params(setup, amount=Decimal("-10.5")), "ck_transactions_pyg_integer")
    _rejected(
        db,
        _params(setup, voided_at="2026-03-02T00:00:00Z", voided_by=setup["user_id"]),
        "ck_transactions_void_complete",
    )
    _rejected(
        db,
        _params(
            setup,
            voided_at="2026-03-02T00:00:00Z",
            voided_by=setup["user_id"],
            void_reason=" x ",
        ),
        "ck_transactions_void_reason_length",
    )
    _rejected(
        db,
        _params(
            setup,
            category_id=setup["per_category"],
            transfer_group_id="0190a2b4-0000-7000-8000-000000000001",
        ),
        "ck_transactions_transfer_without_category",
    )


def test_category_parent_must_share_context(db: Session, setup: dict[str, Any]) -> None:
    nested = db.begin_nested()
    with pytest.raises(IntegrityError, match="fk_categories_parent_id_categories"):
        db.execute(
            text(
                "INSERT INTO finance.categories (context_id, name, kind, parent_id)"
                " VALUES (:ctx, 'Hija', 'income', :parent)"
            ),
            {"ctx": setup["per"], "parent": setup["biz_category"]},
        )
    nested.rollback()


def test_one_business_context_per_organization(db: Session, setup: dict[str, Any]) -> None:
    nested = db.begin_nested()
    with pytest.raises(IntegrityError, match="uq_contexts_business_per_org"):
        db.execute(
            text(
                "INSERT INTO finance.contexts (organization_id, kind, name)"
                " SELECT organization_id, 'business', 'Otra' FROM finance.contexts LIMIT 1"
            )
        )
    nested.rollback()
    nested = db.begin_nested()
    with pytest.raises(IntegrityError, match="ck_contexts_owner_matches_kind"):
        db.execute(
            text(
                "INSERT INTO finance.contexts (organization_id, kind, name)"
                " SELECT organization_id, 'personal', 'Sin dueño' FROM finance.contexts LIMIT 1"
            )
        )
    nested.rollback()


def test_account_stores_only_last_four_digits(db: Session, setup: dict[str, Any]) -> None:
    nested = db.begin_nested()
    with pytest.raises(IntegrityError, match="ck_accounts_number_last4_digits"):
        db.execute(
            text("UPDATE finance.accounts SET number_last4 = '12a4' WHERE id = :id"),
            {"id": setup["per_account"]},
        )
    nested.rollback()
