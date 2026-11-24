"""El resumen optimizado (una sola pasada, D-033) da exactamente lo mismo que un cálculo de
referencia simple en Python sobre datos variados.

Los movimientos se insertan directo en la base (para tener cientos con fechas y casos
repartidos a propósito); las cuentas y categorías pasan por la API.
"""

import hashlib
import random
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import insert, text, update
from sqlalchemy.orm import Session

from app.modules.finance.models import Account, Transaction
from app.modules.finance.money import format_amount
from tests.conftest import auth_header
from tests.finance_utils import API, business_context, create_account, ok, personal_context

ZERO = Decimal(0)


@dataclass
class Tx:
    account_id: str
    currency: str
    booked_on: date
    amount: Decimal
    category_id: str | None
    transfer_group_id: str | None
    voided: bool


def _random_amount(rng: random.Random, currency: str) -> Decimal:
    magnitude = rng.randint(1, 900)
    value = Decimal(magnitude) * (1000 if currency == "PYG" else 1)
    if currency != "PYG":
        value += Decimal(rng.randint(0, 99)) / 100
    return value if rng.random() < 0.45 else -value


def _seed_transactions(
    db: Session, user_id: uuid.UUID, cid: str, accounts: list[dict[str, Any]], cats: list[str]
) -> list[Tx]:
    """Movimientos variados: fuera de período, anulados, transferencias, con y sin categoría."""
    rng = random.Random(20261124)  # noqa: S311 - datos de prueba, no criptografía
    rows: list[Tx] = []
    by_currency: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for account in accounts:
        by_currency[account["currency"]].append(account)
    first_day = date(2024, 11, 20)
    for _ in range(520):
        account = rng.choice(accounts)
        currency = account["currency"]
        # Se incluyen a propósito los bordes: primer y último día de mes y de períodos.
        day = first_day + timedelta(days=rng.randint(0, 760))
        if rng.random() < 0.15:
            day = date(day.year, day.month, 1) if rng.random() < 0.5 else date(day.year, 12, 31)
        amount = _random_amount(rng, currency)
        category = rng.choice([None, *cats]) if rng.random() < 0.7 else None
        rows.append(Tx(account["id"], currency, day, amount, category, None, rng.random() < 0.08))
    # Transferencias entre dos cuentas de la misma moneda (dos patas, sin categoría).
    pairs = [accs for accs in by_currency.values() if len(accs) >= 2]
    for _ in range(40):
        a, b = rng.sample(rng.choice(pairs), 2)
        day = first_day + timedelta(days=rng.randint(0, 760))
        value = Decimal(rng.randint(1, 50) * 10_000)
        group = str(uuid.uuid4())
        voided = rng.random() < 0.15
        rows.append(Tx(a["id"], a["currency"], day, -value, None, group, voided))
        rows.append(Tx(b["id"], b["currency"], day, value, None, group, voided))
    now = datetime.now(UTC)
    db.execute(
        insert(Transaction),
        [
            {
                "context_id": cid,
                "account_id": t.account_id,
                "currency": t.currency,
                "booked_on": t.booked_on,
                "amount": t.amount,
                "description": f"Referencia {i}",
                "category_id": t.category_id,
                "transfer_group_id": t.transfer_group_id,
                "source": "manual",
                "dedupe_key": hashlib.sha256(f"{cid}{i}".encode()).digest(),
                "created_by": user_id,
                "voided_at": now if t.voided else None,
                "voided_by": user_id if t.voided else None,
                "void_reason": "Anulado de prueba" if t.voided else None,
            }
            for i, t in enumerate(rows)
        ],
    )
    return rows


def _month(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def _reference(
    accounts: list[dict[str, Any]],
    txs: list[Tx],
    names: dict[str, str],
    date_from: date,
    date_to: date,
) -> dict[str, Any]:
    """Cálculo directo, sin agrupar en la base: recorre cada movimiento."""
    live = [t for t in txs if not t.voided]
    balances: dict[str, Decimal] = {a["id"]: Decimal(a["opening_balance"]) for a in accounts}
    for t in live:
        if t.booked_on <= date_to:
            balances[t.account_id] += t.amount
    flows = [
        t
        for t in live
        if t.transfer_group_id is None and date_from <= t.booked_on <= date_to  # sin transfer.
    ]
    income: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    expense: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    months: set[tuple[str, str]] = set()
    per_category: dict[tuple[str, str | None], Decimal] = defaultdict(Decimal)
    for t in flows:
        key = (t.currency, _month(t.booked_on))
        months.add(key)
        if t.amount > 0:
            income[key] += t.amount
        else:
            expense[key] += -t.amount
            per_category[(t.currency, t.category_id)] += -t.amount
    by_month = [
        {
            "currency": c,
            "month": m,
            "income": format_amount(income[(c, m)], c),
            "expense": format_amount(expense[(c, m)], c),
            "net": format_amount(income[(c, m)] - expense[(c, m)], c),
        }
        for c, m in sorted(months)
    ]
    totals = []
    for currency in sorted({c for c, _ in months}):
        inc = sum((v for (c, _), v in income.items() if c == currency), ZERO)
        exp = sum((v for (c, _), v in expense.items() if c == currency), ZERO)
        totals.append(
            {
                "currency": currency,
                "income": format_amount(inc, currency),
                "expense": format_amount(exp, currency),
                "net": format_amount(inc - exp, currency),
            }
        )
    ordered = sorted(
        ((c, cat, v) for (c, cat), v in per_category.items()),
        key=lambda r: (r[0], -r[2], names[r[1]] if r[1] else "Sin categoría"),
    )
    categories = [
        {
            "currency": c,
            "category_id": cat,
            "category_name": names[cat] if cat else "Sin categoría",
            "amount": format_amount(v, c),
        }
        for c, cat, v in ordered
    ]
    return {
        "balances": {a["id"]: format_amount(balances[a["id"]], a["currency"]) for a in accounts},
        "totals": totals,
        "by_month": by_month,
        "expenses_by_category": categories,
    }


def _check(
    client: TestClient,
    token: str,
    cid: str,
    accounts: list[dict[str, Any]],
    txs: list[Tx],
    names: dict[str, str],
    **period: str,
) -> None:
    res = ok(client.get(f"{API}/contexts/{cid}/summary", params=period, headers=auth_header(token)))
    date_from = date.fromisoformat(res["date_from"])
    date_to = date.fromisoformat(res["date_to"])
    expected = _reference(accounts, txs, names, date_from, date_to)
    assert {b["account_id"]: b["balance"] for b in res["balances"]} == expected["balances"]
    assert res["totals"] == expected["totals"]
    assert res["by_month"] == expected["by_month"]
    assert res["expenses_by_category"] == expected["expenses_by_category"]


def _setup_context(
    client: TestClient,
    db: Session,
    token: str,
    cid: str,
    user_id: uuid.UUID,
    prefix: str,
) -> tuple[list[dict[str, Any]], list[Tx], dict[str, str]]:
    specs = [
        ("PYG", "1500000"),
        ("PYG", "0"),
        ("PYG", "250000"),
        ("USD", "1200.50"),
        ("USD", "0.00"),
        ("EUR", "99.99"),  # moneda con una sola cuenta: sin transferencias
        ("BRL", "0.00"),  # cuenta sin movimientos en absoluto
    ]
    accounts = [
        create_account(
            client,
            token,
            cid,
            f"{prefix} cuenta {i}",
            currency=currency,
            opening_balance=opening,
            opening_date="2024-01-01",
        )
        for i, (currency, opening) in enumerate(specs)
    ]
    # La cuenta BRL no recibe movimientos: queda con su saldo inicial.
    cats: list[str] = []
    names: dict[str, str] = {}
    headers = auth_header(token)
    for name in ("Insumos", "Servicios", "Ventas"):
        body: dict[str, Any] = {"name": f"{prefix} {name}", "kind": "expense"}
        cat = ok(client.post(f"{API}/contexts/{cid}/categories", json=body, headers=headers), 201)
        names[cat["id"]] = cat["name"]
        cats.append(cat["id"])
        for sub in ("Fijos", "Variables"):
            child = ok(
                client.post(
                    f"{API}/contexts/{cid}/categories",
                    json={"name": f"{name} {sub}", "kind": "expense", "parent_id": cat["id"]},
                    headers=headers,
                ),
                201,
            )
            names[child["id"]] = child["name"]
            cats.append(child["id"])
    txs = _seed_transactions(
        db, user_id, cid, [a for a in accounts if a["currency"] != "BRL"], cats
    )
    # Una cuenta archivada igual cuenta en los saldos.
    db.execute(
        update(Account).where(Account.id == accounts[1]["id"]).values(archived_at=datetime.now(UTC))
    )
    return accounts, txs, names


def test_summary_matches_python_reference(
    client: TestClient, owner_token: str, db: Session
) -> None:
    user_id = db.scalar(text("SELECT id FROM core.users WHERE email = 'owner@example.com'"))
    assert user_id is not None
    biz = business_context(client, owner_token)
    accounts, txs, names = _setup_context(client, db, owner_token, biz, user_id, "Emp")

    periods: list[dict[str, str]] = [
        {"from": "2025-12-01", "to": "2026-11-30"},  # 12 meses completos
        {"from": "2025-06-15", "to": "2026-03-10"},  # bordes a mitad de mes
        {"from": "2026-01-01", "to": "2026-01-31"},  # un solo mes
        {"from": "2026-02-28", "to": "2026-02-28"},  # un solo día
        {"from": "2020-01-01", "to": "2023-12-31"},  # antes de todo movimiento
        {"from": "2024-01-01", "to": "2027-06-30"},  # todo
        {"to": "2026-08-31"},  # `from` por defecto (12 meses hacia atrás)
        {},  # por defecto: hasta hoy
    ]
    assert len(txs) > 500
    assert any(t.voided for t in txs) and any(t.transfer_group_id for t in txs)
    for period in periods:
        _check(client, owner_token, biz, accounts, txs, names, **period)
    # El cálculo de referencia no es trivial: hay 12 meses por moneda y gastos categorizados.
    year = _reference(accounts, txs, names, date(2025, 12, 1), date(2026, 11, 30))
    assert len([m for m in year["by_month"] if m["currency"] == "PYG"]) == 12
    assert {c["currency"] for c in year["totals"]} == {"PYG", "USD", "EUR"}
    assert any(c["category_id"] for c in year["expenses_by_category"])
    assert any(c["category_id"] is None for c in year["expenses_by_category"])


def test_consolidated_matches_python_reference(
    client: TestClient, owner_token: str, db: Session
) -> None:
    """El consolidado (sin categorías) usa la misma pasada y no se mezcla entre contextos."""
    user_id = db.scalar(text("SELECT id FROM core.users WHERE email = 'owner@example.com'"))
    assert user_id is not None
    biz = business_context(client, owner_token)
    personal = personal_context(client, owner_token)
    data = {
        biz: _setup_context(client, db, owner_token, biz, user_id, "Emp"),
        personal: _setup_context(client, db, owner_token, personal, user_id, "Per"),
    }
    res = ok(
        client.get(
            f"{API}/summary/consolidated",
            params={"from": "2025-12-01", "to": "2026-11-30"},
            headers=auth_header(owner_token),
        )
    )
    assert {c["context"]["id"] for c in res["contexts"]} == {biz, personal}
    for entry in res["contexts"]:
        accounts, txs, names = data[entry["context"]["id"]]
        expected = _reference(accounts, txs, names, date(2025, 12, 1), date(2026, 11, 30))
        balance_by_currency: dict[str, Decimal] = defaultdict(Decimal)
        for a in accounts:
            balance_by_currency[a["currency"]] += Decimal(expected["balances"][a["id"]])
        flows = {t["currency"]: t for t in expected["totals"]}
        currencies = sorted(set(balance_by_currency) | set(flows))
        assert [t["currency"] for t in entry["totals"]] == currencies
        for total in entry["totals"]:
            currency = total["currency"]
            assert total["balance"] == format_amount(balance_by_currency[currency], currency)
            reference_flow = flows.get(currency)
            assert total["income"] == (
                reference_flow["income"] if reference_flow else format_amount(ZERO, currency)
            )
            assert total["expense"] == (
                reference_flow["expense"] if reference_flow else format_amount(ZERO, currency)
            )
            assert total["net"] == (
                reference_flow["net"] if reference_flow else format_amount(ZERO, currency)
            )
