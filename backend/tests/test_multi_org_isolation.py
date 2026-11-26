"""Aislamiento entre organizaciones (fase M1 del plan multiempresa).

La organización A carga datos de todos los módulos; la B, con su propio propietario y sesión
(`other_org`), intenta leerlos, tocarlos y referenciarlos desde los suyos. Las tablas de
sondeo enumeran cada ruta con un id en el camino; `test_every_route_with_an_id_is_probed`
falla si aparece una ruta nueva sin cubrir.
"""

import json
import re
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.main import create_app
from app.modules.marangatu import service as marangatu_service
from app.modules.marangatu import storage
from app.modules.marangatu.models import Run
from tests.accounting_utils import (
    ACC,
    ALQUILERES,
    BANCOS,
    CAJA,
    CAPITAL,
    GRUPO_DISPONIBILIDADES,
    PROVEEDORES,
    draft,
)
from tests.assets_utils import MUEBLES, new_asset, run_and_post, setup_books
from tests.conftest import STRONG_PASSWORD, OtherOrg, auth_header
from tests.finance_utils import (
    API as FIN,
)
from tests.finance_utils import (
    create_account,
    create_tx,
    ok,
)
from tests.marangatu_utils import MARANGATU, BotEnv, bot_env, enable_bot  # noqa: F401 - fixture
from tests.tax_utils import (
    TAX,
    create_voucher,
    obligation,
    setup_tax,
)

V1 = "/api/v1"
# Solo UUID v7 (los ids de la base): una URL de la normativa puede traer otros UUID.
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[0-9a-f]{4}-[0-9a-f]{12}")
HIDDEN = (403, 404)
REJECTED = (403, 404, 409, 422)

IMPORT_MAPPING = {
    "has_header": True,
    "delimiter": ";",
    "encoding": "utf-8",
    "date_column": "Fecha",
    "date_format": "%d/%m/%Y",
    "description_column": "Concepto",
    "amount": {"mode": "single", "column": "Importe"},
    "decimal_separator": ",",
    "thousands_separator": ".",
    "skip_rows": 0,
}
IMPORT_CSV = "Fecha;Concepto;Importe\n05/03/2026;Pago ANDE;-150.000\n06/03/2026;Cobro;200.000\n"

World = dict[str, Any]
Body = dict[str, Any] | Callable[[World], dict[str, Any]] | None


# --- Mundos: A (datos en todos los módulos) y B (lo mínimo para operar con lo propio) -----


def _lines(w: World, *, own: bool = False) -> list[dict[str, str]]:
    return [
        {"account_id": w["acc_caja"], "debit": "1000"},
        {"account_id": w["acc_capital"], "credit": "1000"},
    ]


def _books(client: TestClient, token: str, monkeypatch: pytest.MonkeyPatch, ruc: str) -> World:
    """Plan de cuentas, ejercicio, categorías de bienes, centro de costo y datos de tributación."""
    books = setup_books(client, token)
    setup_tax(client, token, monkeypatch, ruc=ruc)
    accounts = books["accounts"]
    year = books["years"][2026]
    center = ok(
        client.post(
            f"{ACC}/cost-centers",
            json={"code": "CC1", "name": "Central"},
            headers=auth_header(token),
        ),
        201,
    )
    return {
        "token": token,
        "books": books,
        "acc_caja": accounts[CAJA]["id"],
        "acc_bancos": accounts[BANCOS]["id"],
        "acc_capital": accounts[CAPITAL]["id"],
        "acc_alquileres": accounts[ALQUILERES]["id"],
        "acc_proveedores": accounts[PROVEEDORES]["id"],
        "acc_group": accounts[GRUPO_DISPONIBILIDADES]["id"],
        "fiscal_year_id": year["id"],
        "period_id": year["periods"][2]["id"],
        "period_id_4": year["periods"][3]["id"],
        "center_id": center["id"],
        "asset_category_id": books["categories"][MUEBLES]["id"],
    }


def _finance(client: TestClient, w: World, cid: str) -> None:
    token = w["token"]
    account = create_account(client, token, cid, "Banco")
    other = create_account(client, token, cid, "Caja chica")
    headers = auth_header(token)
    category = ok(
        client.post(
            f"{FIN}/contexts/{cid}/categories",
            json={"name": "Servicios", "kind": "expense"},
            headers=headers,
        ),
        201,
    )
    counterparty = ok(
        client.post(
            f"{FIN}/contexts/{cid}/counterparties",
            json={"name": "ANDE", "kind": "supplier"},
            headers=headers,
        ),
        201,
    )
    tx = create_tx(client, token, cid, account["id"], "-50000", description="Pago de luz")
    batch = ok(
        client.post(
            f"{FIN}/contexts/{cid}/imports",
            files={"file": ("extracto.csv", IMPORT_CSV.encode(), "application/octet-stream")},
            data={"account_id": account["id"], "mapping": json.dumps(IMPORT_MAPPING)},
            headers=headers,
        ),
        201,
    )
    w.update(
        cid=cid,
        account_id=account["id"],
        account2_id=other["id"],
        category_id=category["id"],
        counterparty_id=counterparty["id"],
        transaction_id=tx["id"],
        batch_id=batch["id"],
        row_number=1,
    )


def _world(
    client: TestClient, token: str, cid: str, monkeypatch: pytest.MonkeyPatch, ruc: str, tag: str
) -> World:
    w = _books(client, token, monkeypatch, ruc)
    _finance(client, w, cid)
    headers = auth_header(token)
    entry = draft(
        client, token, w["books"]["accounts"], "2026-03-10", [(CAJA, 500, 0), (CAPITAL, 0, 500)]
    )
    w["entry_id"] = entry["id"]
    asset = new_asset(client, w["books"], name=f"Bien {tag}")
    w["asset_id"] = asset["id"]
    run = run_and_post(client, w["books"], 2026, 2)
    w["run_id"] = run["id"]
    template = ok(
        client.post(
            f"{ACC}/recurring",
            json={
                "description": f"Alquiler {tag}",
                "day_of_month": 28,
                "start_date": "2026-01-01",
                "lines": _lines(w),
            },
            headers=headers,
        ),
        201,
    )
    w["template_id"] = template["id"]
    # Tributación: perfil, obligaciones y un comprobante.
    version = ok(client.get(f"{TAX}/profile", headers=headers))["current"]
    w["profile_id"] = version["id"]
    w["obligation_id"] = obligation(client, token, "IVA-GENERAL-LIQUIDACION", "2026-09-01")["id"]
    ok(
        client.post(
            f"{TAX}/obligations/{w['obligation_id']}/file",
            json={"filed_on": "2026-11-10", "filing_reference": f"TALON-{tag}"},
            headers=headers,
        )
    )
    w["voucher_id"] = create_voucher(
        client, token, number=f"001-001-{9000001 if tag == 'A' else 9000002}"
    )["id"]
    w["user_id"] = ""
    return w


@pytest.fixture
def worlds(
    client: TestClient,
    owner_token: str,
    other_org: OtherOrg,
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
    bot_env: BotEnv,  # noqa: F811
) -> tuple[World, World]:
    """(A, B): cada una con datos propios en todos los módulos."""
    a_cid = next(
        c["id"]
        for c in ok(client.get(f"{FIN}/contexts", headers=auth_header(owner_token)))
        if c["kind"] == "business"
    )
    a = _world(client, owner_token, a_cid, monkeypatch, "80000005", "A")
    b = _world(client, other_org.token, other_org.business_context_id, monkeypatch, "80000013", "B")
    # Un usuario más en A, para probar `PATCH /users/{id}`.
    created = ok(
        client.post(
            f"{V1}/users",
            json={
                "email": "contadora-a@example.com",
                "full_name": "Contadora de A",
                "password": STRONG_PASSWORD,
                "role": "viewer",
            },
            headers=auth_header(owner_token),
        ),
        201,
    )
    a["user_id"] = created["user"]["id"]
    # Bot de Marangatu: una corrida con un paso con captura en A.
    enable_bot(client, owner_token)
    run = ok(client.post(f"{MARANGATU}/runs/reconnaissance", headers=auth_header(owner_token)), 202)
    a["marangatu_run_id"] = run["id"]
    row = db.get(Run, run["id"])
    assert row is not None
    shot = storage.run_dir(row.organization_id, row.id) / "001-ingreso.png"
    shot.parent.mkdir(parents=True, exist_ok=True)
    shot.write_bytes(b"captura de A")
    step = marangatu_service.add_step(
        db,
        row,
        action="captura",
        capture_path=storage.relative(shot),
        capture_sha256=storage.sha256_file(shot),
    )
    db.commit()
    a["step_id"] = str(step.id)
    return a, b


def _a_ids(a: World) -> set[str]:
    """Todos los ids de A que ningún cuerpo de respuesta de B puede contener."""
    found: set[str] = set()
    for value in a.values():
        found.update(UUID_RE.findall(json.dumps(value, default=str)))
    return found


def _call(
    client: TestClient, token: str, method: str, path: str, body: dict[str, Any] | None = None
) -> Any:
    kwargs: dict[str, Any] = {"headers": auth_header(token)}
    if body is not None:
        kwargs["json"] = body
    return client.request(method, f"{V1}{path}", **kwargs)


def _body(body: Body, w: World) -> dict[str, Any] | None:
    return body(w) if callable(body) else body


def _assert_no_leak(res: Any, a: World, label: str) -> None:
    leaked = [i for i in _a_ids(a) if i in res.text]
    names = [k for k, v in a.items() if any(i in json.dumps(v, default=str) for i in leaked)]
    assert not leaked, f"{label}: la respuesta de B contiene ids de A {names}: {res.text[:300]}"


# --- Sondeos por id: método, ruta (con los nombres de parámetro de la ruta) y cuerpo -----------

NAME = {"name": "Cambiado por B"}
REASON = {"reason": "Intento de la otra organización"}
ENTRY_BODY: Callable[[World], dict[str, Any]] = lambda w: {  # noqa: E731
    "entry_date": "2026-03-10",
    "description": "Cambiado por B",
    "lines": _lines(w),
}

Probe = tuple[str, str, Body]

FINANCE_PROBES: list[Probe] = [
    ("PATCH", "/finance/contexts/{cid}/accounts/{account_id}", NAME),
    ("PATCH", "/finance/contexts/{cid}/categories/{category_id}", NAME),
    ("PATCH", "/finance/contexts/{cid}/counterparties/{counterparty_id}", NAME),
    ("GET", "/finance/contexts/{cid}/transactions/{transaction_id}", None),
    ("PATCH", "/finance/contexts/{cid}/transactions/{transaction_id}", {"description": "Cambiado"}),
    ("POST", "/finance/contexts/{cid}/transactions/{transaction_id}/void", REASON),
    ("GET", "/finance/contexts/{cid}/imports/{batch_id}", None),
    ("PATCH", "/finance/contexts/{cid}/imports/{batch_id}/rows/{row_number}", {"decision": "skip"}),
    ("POST", "/finance/contexts/{cid}/imports/{batch_id}/commit", None),
    ("POST", "/finance/contexts/{cid}/imports/{batch_id}/cancel", None),
]
# Rutas con el contexto de A y nada más: listas y resumen del contexto ajeno.
FINANCE_CONTEXT_PROBES: list[Probe] = [
    ("GET", "/finance/contexts/{cid}/accounts", None),
    ("GET", "/finance/contexts/{cid}/categories", None),
    ("GET", "/finance/contexts/{cid}/counterparties", None),
    ("GET", "/finance/contexts/{cid}/transactions", None),
    ("GET", "/finance/contexts/{cid}/imports", None),
    ("GET", "/finance/contexts/{cid}/summary", None),
    ("POST", "/finance/contexts/{cid}/categories/suggested", None),
    (
        "POST",
        "/finance/contexts/{cid}/accounts",
        {
            "name": "Cuenta de B",
            "kind": "checking",
            "currency": "PYG",
            "opening_date": "2026-01-01",
        },
    ),
    ("POST", "/finance/contexts/{cid}/categories", {"name": "Categoría de B", "kind": "expense"}),
    (
        "POST",
        "/finance/contexts/{cid}/counterparties",
        {"name": "Contraparte de B", "kind": "other"},
    ),
    (
        "POST",
        "/finance/contexts/{cid}/transactions",
        lambda w: {
            "account_id": w["account_id"],
            "booked_on": "2026-03-11",
            "amount": "-1000",
            "description": "Movimiento de B",
        },
    ),
    (
        "POST",
        "/finance/contexts/{cid}/transfers",
        lambda w: {
            "from_account_id": w["account_id"],
            "to_account_id": w["account2_id"],
            "booked_on": "2026-03-11",
            "amount_out": "1000",
            "amount_in": "1000",
            "description": "Traspaso de B",
        },
    ),
]
ACCOUNTING_PROBES: list[Probe] = [
    ("PATCH", "/accounting/chart/accounts/{account_id}", NAME),
    ("GET", "/accounting/fiscal-years/{fiscal_year_id}", None),
    ("POST", "/accounting/fiscal-years/{fiscal_year_id}/close", None),
    ("POST", "/accounting/periods/{period_id}/close", None),
    ("POST", "/accounting/periods/{period_id}/reopen", REASON),
    ("POST", "/accounting/entries/from-transaction/{transaction_id}", None),
    ("GET", "/accounting/entries/{entry_id}", None),
    ("PATCH", "/accounting/entries/{entry_id}", ENTRY_BODY),
    ("POST", "/accounting/entries/{entry_id}/post", None),
    ("POST", "/accounting/entries/{entry_id}/reverse", REASON),
    ("POST", "/accounting/entries/{entry_id}/discard", REASON),
    ("GET", "/accounting/reports/ledger/{account_id}?from=2026-01-01&to=2026-12-31", None),
    ("GET", "/accounting/asset-categories/{category_id}", None),
    ("PATCH", "/accounting/asset-categories/{category_id}", NAME),
    ("POST", "/accounting/asset-categories/{category_id}/validate", None),
    ("GET", "/accounting/fixed-assets/{asset_id}", None),
    ("PATCH", "/accounting/fixed-assets/{asset_id}", NAME),
    (
        "POST",
        "/accounting/fixed-assets/{asset_id}/dispose",
        {
            "date": "2026-03-20",
            "kind": "sale",
            "reason": "Venta del bien",
            "document_reference": "Acta 1/2026",
        },
    ),
    ("GET", "/accounting/depreciation/runs/{run_id}", None),
    ("GET", "/accounting/cost-centers/{center_id}", None),
    ("PATCH", "/accounting/cost-centers/{center_id}", NAME),
    ("GET", "/accounting/recurring/{template_id}", None),
    ("PATCH", "/accounting/recurring/{template_id}", {"description": "Cambiado por B"}),
]
TAX_PROBES: list[Probe] = [
    (
        "POST",
        "/tax/profile/{profile_id}/verify",
        {"verified_document_reference": "Constancia de B"},
    ),
    (
        "POST",
        "/tax/obligations/{obligation_id}/file",
        {"filed_on": "2026-11-10", "filing_reference": "TALON-B"},
    ),
    ("POST", "/tax/obligations/{obligation_id}/pay", {"paid_on": "2026-11-10", "paid_amount": "1"}),
    ("POST", "/tax/obligations/{obligation_id}/not-applicable", REASON),
    ("POST", "/tax/obligations/{obligation_id}/reopen", REASON),
    ("GET", "/tax/vouchers/{voucher_id}", None),
    ("PATCH", "/tax/vouchers/{voucher_id}", {"notes": "Cambiado por B"}),
    ("POST", "/tax/vouchers/{voucher_id}/void", REASON),
    (
        "POST",
        "/tax/vouchers/{voucher_id}/propose-entry",
        lambda w: {"account_id": w["acc_caja"]},
    ),
]
MARANGATU_PROBES: list[Probe] = [
    ("GET", "/marangatu/runs/{run_id}", None),
    ("GET", "/marangatu/steps/{step_id}/capture", None),
]
IDENTITY_PROBES: list[Probe] = [("PATCH", "/users/{user_id}", {"is_active": False})]

# Rutas con id en el camino que NO son de una organización, y por qué.
EXEMPT = {
    # Subida de archivo (multipart): la cubre `test_import_upload_into_context_of_a`.
    ("POST", "/finance/contexts/{cid}/imports"),
    # Catálogo normativo compartido de la instalación (reglas, feriados y excepciones de
    # vencimiento: leyes y decretos del país, sin `organization_id`).
    ("POST", "/tax/rules/{rule_id}/verify"),
    ("POST", "/tax/rules/{rule_id}/deprecate"),
    ("PATCH", "/tax/holidays/{holiday_id}"),
    ("DELETE", "/tax/holidays/{holiday_id}"),
    ("PATCH", "/tax/due-date-exceptions/{exception_id}"),
    # Año y mes, no ids: calcula siempre sobre la organización de la sesión.
    ("GET", "/tax/vat/{year}/{month}"),
    ("POST", "/tax/vat/{year}/{month}/apply"),
}
ALL_ID_PROBES = [
    *FINANCE_PROBES,
    *FINANCE_CONTEXT_PROBES,
    *ACCOUNTING_PROBES,
    *TAX_PROBES,
    *MARANGATU_PROBES,
    *IDENTITY_PROBES,
]


def test_every_route_with_an_id_is_probed() -> None:
    paths = create_app().openapi()["paths"]
    routes = {
        (method.upper(), path.removeprefix(V1))
        for path, operations in paths.items()
        if "{" in path
        for method in operations
    }
    probed = {(m, p.split("?")[0]) for m, p, _ in ALL_ID_PROBES} | EXEMPT
    assert routes - probed == set(), "rutas con id sin sondeo de aislamiento"
    assert probed - routes == set(), "sondeos de rutas que ya no existen"


def _run_probes(
    client: TestClient, token: str, probes: list[Probe], a: World, b: World, use: World
) -> None:
    """Llama cada ruta con los ids de `use` y exige 403/404, sin ids de A en la respuesta."""
    for method, path, body in probes:
        # Con lo propio de B el sondeo no puede dar 404 por error de ruta: el cuerpo es el de B.
        res = _call(client, token, method, path.format(**use), _body(body, b))
        label = f"{method} {path}"
        assert res.status_code in HIDDEN, f"{label}: {res.status_code} {res.text[:300]}"
        _assert_no_leak(res, a, label)


def _snapshot(client: TestClient, token: str, a: World) -> dict[str, Any]:
    """Lo que A ve de sus datos (para comprobar que B no cambió nada)."""
    paths = [
        f"/finance/contexts/{a['cid']}/accounts",
        f"/finance/contexts/{a['cid']}/categories",
        f"/finance/contexts/{a['cid']}/counterparties",
        f"/finance/contexts/{a['cid']}/transactions?limit=200",
        f"/finance/contexts/{a['cid']}/imports",
        "/accounting/chart?flat=true",
        "/accounting/fiscal-years",
        "/accounting/entries",
        "/accounting/fixed-assets",
        "/accounting/cost-centers",
        "/accounting/recurring",
        "/accounting/depreciation/runs",
        "/tax/profile",
        "/tax/obligations",
        "/tax/vouchers",
        "/users",
        "/organization",
    ]
    out = {}
    for path in paths:
        res = _call(client, token, "GET", path)
        assert res.status_code == 200, f"{path}: {res.text[:200]}"
        out[path] = res.json()
    return out


@pytest.mark.parametrize("own_context", [False, True], ids=["contexto_ajeno", "contexto_propio"])
def test_finance_ids_of_another_organization(
    client: TestClient, other_org: OtherOrg, worlds: tuple[World, World], own_context: bool
) -> None:
    """Con el contexto de A o con el propio de B, los ids de A no existen para B."""
    a, b = worlds
    use = {**a, "cid": b["cid"]} if own_context else a
    _run_probes(client, other_org.token, FINANCE_PROBES, a, b, use)
    if not own_context:
        _run_probes(client, other_org.token, FINANCE_CONTEXT_PROBES, a, b, use)


def test_import_upload_into_context_of_a(
    client: TestClient, other_org: OtherOrg, worlds: tuple[World, World]
) -> None:
    a, b = worlds
    for cid in (a["cid"], b["cid"]):
        res = client.post(
            f"{FIN}/contexts/{cid}/imports",
            files={"file": ("extracto.csv", IMPORT_CSV.encode(), "application/octet-stream")},
            data={"account_id": a["account_id"], "mapping": json.dumps(IMPORT_MAPPING)},
            headers=auth_header(other_org.token),
        )
        assert res.status_code in REJECTED, f"{cid}: {res.status_code} {res.text[:300]}"


@pytest.mark.parametrize(
    "probes",
    [ACCOUNTING_PROBES, TAX_PROBES, MARANGATU_PROBES, IDENTITY_PROBES],
    ids=["contabilidad", "tributacion", "marangatu", "usuarios"],
)
def test_ids_of_another_organization_are_hidden(
    client: TestClient,
    owner_token: str,
    other_org: OtherOrg,
    worlds: tuple[World, World],
    probes: list[Probe],
) -> None:
    a, b = worlds
    before = _snapshot(client, owner_token, a)
    # `run_id` es la corrida de depreciación en contabilidad y la del bot en Marangatu.
    use = {**a, "run_id": a["marangatu_run_id"]} if probes is MARANGATU_PROBES else a
    _run_probes(client, other_org.token, probes, a, b, use)
    assert _snapshot(client, owner_token, a) == before, "B cambió datos de A"


def test_other_org_attempts_do_not_change_organization_a(
    client: TestClient, owner_token: str, other_org: OtherOrg, worlds: tuple[World, World]
) -> None:
    """Tras todos los intentos de B, A conserva sus datos y sus asientos siguen en borrador."""
    a, b = worlds
    before = _snapshot(client, owner_token, a)
    use = {**a, "cid": a["cid"]}
    for probes in (FINANCE_PROBES, FINANCE_CONTEXT_PROBES, ACCOUNTING_PROBES, TAX_PROBES):
        _run_probes(client, other_org.token, probes, a, b, use)
    assert _snapshot(client, owner_token, a) == before
    entry = ok(client.get(f"{ACC}/entries/{a['entry_id']}", headers=auth_header(owner_token)))
    assert entry["status"] == "draft"


# --- Listas: cada una solo trae lo propio ------------------------------------------------------

LISTS = [
    "/users",
    "/organization",
    "/finance/contexts",
    "/finance/contexts/{cid}/accounts",
    "/finance/contexts/{cid}/categories",
    "/finance/contexts/{cid}/counterparties",
    "/finance/contexts/{cid}/transactions",
    "/finance/contexts/{cid}/imports",
    "/finance/contexts/{cid}/summary",
    "/finance/summary/consolidated",
    "/accounting/chart?flat=true",
    "/accounting/settings",
    "/accounting/fiscal-years",
    "/accounting/entries",
    "/accounting/reports/journal?from=2026-01-01&to=2026-12-31",
    "/accounting/reports/trial-balance?from=2026-01-01&to=2026-12-31",
    "/accounting/reports/balance-sheet?at=2026-12-31",
    "/accounting/reports/income-statement?from=2026-01-01&to=2026-12-31",
    "/accounting/asset-categories",
    "/accounting/fixed-assets",
    "/accounting/depreciation/runs",
    "/accounting/reports/depreciation-schedule?fiscal_year_id={fiscal_year_id}",
    "/accounting/cost-centers",
    "/accounting/recurring",
    "/tax/profile",
    "/tax/obligations",
    "/tax/vouchers",
    "/tax/vouchers/export?year=2026&month=10",
    "/tax/alerts",
    "/tax/settings",
    "/marangatu/settings",
    "/marangatu/credentials",
    "/marangatu/runs",
    "/audit/logs?limit=200",
    "/audit/security-events?limit=200",
]


@pytest.mark.parametrize("path", LISTS)
def test_lists_of_b_hold_nothing_of_a(
    client: TestClient, other_org: OtherOrg, worlds: tuple[World, World], path: str
) -> None:
    a, b = worlds
    res = _call(client, other_org.token, "GET", path.format(**b))
    assert res.status_code == 200, f"{path}: {res.status_code} {res.text[:300]}"
    _assert_no_leak(res, a, path)
    # El nombre de lo que cargó A tampoco aparece (por si un id se reescribiera).
    for marker in ("Alquiler A", "Bien A", "contadora-a@example.com", "Empresa de Prueba EAS"):
        assert marker not in res.text, f"{path}: aparece «{marker}» de A"


def test_filters_by_ids_of_a_return_nothing_to_b(
    client: TestClient, other_org: OtherOrg, worlds: tuple[World, World]
) -> None:
    a, b = worlds
    for path in (
        f"/accounting/entries?fiscal_year_id={a['fiscal_year_id']}",
        f"/accounting/entries?account_id={a['acc_caja']}",
        f"/accounting/fixed-assets?category_id={a['asset_category_id']}",
        f"/accounting/depreciation/runs?fiscal_year_id={a['fiscal_year_id']}",
        f"/accounting/recurring/due?period_id={a['period_id']}",
        f"/finance/contexts/{b['cid']}/transactions?account_id={a['account_id']}",
    ):
        res = _call(client, other_org.token, "GET", path)
        assert res.status_code in (200, *REJECTED), f"{path}: {res.status_code}"
        if res.status_code == 200:
            _assert_no_leak(res, a, path)


# --- Referencias cruzadas al crear: B no puede apuntar a ids de A -------------------------------

Build = Callable[[World], dict[str, Any]]
# (etiqueta, método, ruta, cuerpo con los ids de B, clave del id de A que se cuela).
References: list[tuple[str, str, str, Build, str]] = [
    (
        "movimiento con cuenta de A",
        "POST",
        "/finance/contexts/{cid}/transactions",
        lambda w: {
            "account_id": w["account_id"],
            "booked_on": "2026-03-11",
            "amount": "-1000",
            "description": "Movimiento",
        },
        "account_id",
    ),
    (
        "movimiento con categoría de A",
        "POST",
        "/finance/contexts/{cid}/transactions",
        lambda w: {
            "account_id": w["account_id"],
            "booked_on": "2026-03-11",
            "amount": "-1000",
            "description": "Movimiento",
            "category_id": w["category_id"],
        },
        "category_id",
    ),
    (
        "movimiento con contraparte de A",
        "POST",
        "/finance/contexts/{cid}/transactions",
        lambda w: {
            "account_id": w["account_id"],
            "booked_on": "2026-03-11",
            "amount": "-1000",
            "description": "Movimiento",
            "counterparty_id": w["counterparty_id"],
        },
        "counterparty_id",
    ),
    (
        "transferencia con cuenta de A",
        "POST",
        "/finance/contexts/{cid}/transfers",
        lambda w: {
            "from_account_id": w["account_id"],
            "to_account_id": w["account2_id"],
            "booked_on": "2026-03-11",
            "amount_out": "1000",
            "amount_in": "1000",
            "description": "Traspaso",
        },
        "account2_id",
    ),
    (
        "cuenta bancaria vinculada a cuenta contable de A",
        "PATCH",
        "/finance/contexts/{cid}/accounts/{account_id}",
        lambda w: {"ledger_account_id": w["acc_bancos"]},
        "acc_bancos",
    ),
    (
        "categoría vinculada a cuenta contable de A",
        "PATCH",
        "/finance/contexts/{cid}/categories/{category_id}",
        lambda w: {"ledger_account_id": w["acc_alquileres"]},
        "acc_alquileres",
    ),
    (
        "categoría hija de una categoría de A",
        "POST",
        "/finance/contexts/{cid}/categories",
        lambda w: {"name": "Hija", "kind": "expense", "parent_id": w["category_id"]},
        "category_id",
    ),
    (
        "asiento con cuenta contable de A",
        "POST",
        "/accounting/entries",
        lambda w: {
            "entry_date": "2026-03-12",
            "description": "Asiento",
            "lines": [
                {"account_id": w["acc_caja"], "debit": "100"},
                {"account_id": w["acc_capital"], "credit": "100"},
            ],
        },
        "acc_caja",
    ),
    (
        "asiento con centro de costo de A",
        "POST",
        "/accounting/entries",
        lambda w: {
            "entry_date": "2026-03-12",
            "description": "Asiento",
            "lines": [
                {
                    "account_id": w["acc_alquileres"],
                    "debit": "100",
                    "cost_center_id": w["center_id"],
                },
                {"account_id": w["acc_capital"], "credit": "100"},
            ],
        },
        "center_id",
    ),
    (
        "cuenta contable hija de una cuenta de A",
        "POST",
        "/accounting/chart/accounts",
        lambda w: {
            "parent_id": w["acc_group"],
            "code": "1.01.01.99",
            "name": "Hija",
            "is_postable": True,
        },
        "acc_group",
    ),
    (
        "ajustes contables con cuenta de A",
        "PUT",
        "/accounting/settings",
        lambda w: {"retained_earnings_account_id": w["acc_capital"]},
        "acc_capital",
    ),
    (
        "categoría de bienes con cuenta de A",
        "POST",
        "/accounting/asset-categories",
        lambda w: {"name": "Propia", "asset_account_id": w["acc_caja"]},
        "acc_caja",
    ),
    (
        "bien con categoría de A",
        "POST",
        "/accounting/fixed-assets",
        lambda w: {
            "category_id": w["asset_category_id"],
            "name": "Bien",
            "acquired_on": "2026-02-01",
            "cost": "1000000",
        },
        "asset_category_id",
    ),
    (
        "bien con asiento de adquisición de A",
        "POST",
        "/accounting/fixed-assets",
        lambda w: {
            "category_id": w["asset_category_id"],
            "name": "Bien",
            "acquired_on": "2026-02-01",
            "cost": "1000000",
            "acquisition_entry_id": w["entry_id"],
        },
        "entry_id",
    ),
    (
        "bien con movimiento de origen de A",
        "POST",
        "/accounting/fixed-assets",
        lambda w: {
            "category_id": w["asset_category_id"],
            "name": "Bien",
            "acquired_on": "2026-02-01",
            "cost": "1000000",
            "source_transaction_id": w["transaction_id"],
        },
        "transaction_id",
    ),
    (
        "depreciación de un período de A",
        "POST",
        "/accounting/depreciation/run",
        lambda w: {"period_id": w["period_id"]},
        "period_id",
    ),
    (
        "plantilla recurrente con cuenta de A",
        "POST",
        "/accounting/recurring",
        lambda w: {
            "description": "Recurrente",
            "day_of_month": 5,
            "start_date": "2026-01-01",
            "lines": _lines(w),
        },
        "acc_caja",
    ),
    (
        "generar recurrentes en un período de A",
        "POST",
        "/accounting/recurring/generate",
        lambda w: {"period_id": w["period_id_4"]},
        "period_id_4",
    ),
    (
        "comprobante con movimiento de A",
        "POST",
        "/tax/vouchers",
        lambda w: _voucher(w, transaction_id=w["transaction_id"]),
        "transaction_id",
    ),
    (
        "comprobante con contraparte de finanzas de A",
        "POST",
        "/tax/vouchers",
        lambda w: _voucher(w, finance_counterparty_id=w["counterparty_id"]),
        "counterparty_id",
    ),
    (
        "comprobante relacionado con uno de A",
        "POST",
        "/tax/vouchers",
        lambda w: _voucher(w, voucher_type="credit_note", related_voucher_id=w["voucher_id"]),
        "voucher_id",
    ),
    (
        "ajustes de tributación con cuenta de A",
        "PUT",
        "/tax/settings",
        lambda w: {"suppliers_account_id": w["acc_proveedores"]},
        "acc_proveedores",
    ),
    (
        "pago de obligación con movimiento de A",
        "POST",
        "/tax/obligations/{obligation_id}/pay",
        lambda w: {
            "paid_on": "2026-11-10",
            "paid_amount": "1",
            "transaction_id": w["transaction_id"],
        },
        "transaction_id",
    ),
]
_counter = {"n": 0}


def _voucher(w: World, **extra: Any) -> dict[str, Any]:
    _counter["n"] += 1
    return {
        "direction": "purchase",
        "voucher_type": "invoice",
        "timbrado": "12345678",
        "number": f"001-001-{_counter['n']:07d}",
        "issued_on": "2026-10-15",
        "counterparty_doc_type": "ruc",
        "counterparty_ruc": "44444401",
        "counterparty_ruc_dv": "7",
        "counterparty_name": "Proveedor",
        "condition": "cash",
        "taxed_10": "110000",
        **extra,
    }


@pytest.mark.parametrize("label,method,path,build,key", References, ids=[r[0] for r in References])
def test_b_cannot_reference_ids_of_a(
    client: TestClient,
    other_org: OtherOrg,
    worlds: tuple[World, World],
    label: str,
    method: str,
    path: str,
    build: Build,
    key: str,
) -> None:
    a, b = worlds
    url = path.format(**b)
    # Control: con todo lo propio la misma llamada funciona (no falla por otra causa).
    if method != "PATCH" or "ledger" in str(build(b)):
        control = _call(client, other_org.token, method, url, build(b))
        assert control.status_code in (200, 201), f"control «{label}»: {control.text[:300]}"
    # Con un solo id de A en el cuerpo, se rechaza y no se guarda nada.
    attack = _call(client, other_org.token, method, url, build({**b, key: a[key]}))
    assert attack.status_code in REJECTED, f"«{label}»: {attack.status_code} {attack.text[:300]}"


# --- Identidad, organización y sesiones ---------------------------------------------------------


def test_users_and_organization_are_per_organization(
    client: TestClient, owner_token: str, other_org: OtherOrg, worlds: tuple[World, World]
) -> None:
    a, _ = worlds
    users = ok(client.get(f"{V1}/users", headers=auth_header(other_org.token)))
    assert [u["user"]["id"] for u in users] == [str(other_org.user_id)]
    assert a["user_id"] not in json.dumps(users)
    mine = ok(client.get(f"{V1}/organization", headers=auth_header(other_org.token)))
    assert mine["id"] == str(other_org.organization_id)
    # B cambia su organización: la de A queda igual.
    ok(
        client.patch(
            f"{V1}/organization",
            json={"trade_name": "Marca de B"},
            headers=auth_header(other_org.token),
        )
    )
    theirs = ok(client.get(f"{V1}/organization", headers=auth_header(owner_token)))
    assert theirs["id"] != mine["id"] and theirs["trade_name"] != "Marca de B"
    me = ok(client.get(f"{V1}/auth/me", headers=auth_header(other_org.token)))
    assert me["organization"]["id"] == str(other_org.organization_id)
    # Cerrar la sesión de B no toca la de A.
    assert client.post(f"{V1}/auth/logout", headers=auth_header(other_org.token)).status_code == 204
    assert client.get(f"{V1}/auth/me", headers=auth_header(other_org.token)).status_code == 401
    assert client.get(f"{V1}/auth/me", headers=auth_header(owner_token)).status_code == 200


def test_b_cannot_create_a_user_with_the_email_of_a(
    client: TestClient, other_org: OtherOrg, owner_token: str
) -> None:
    res = client.post(
        f"{V1}/users",
        json={
            "email": "owner@example.com",
            "full_name": "Intruso",
            "password": STRONG_PASSWORD,
            "role": "viewer",
        },
        headers=auth_header(other_org.token),
    )
    assert res.status_code in (409, 422)


# --- Auditoría ----------------------------------------------------------------------------------


def test_audit_logs_are_per_organization(
    client: TestClient, owner_token: str, other_org: OtherOrg, worlds: tuple[World, World]
) -> None:
    a, b = worlds
    logs_b = ok(
        client.get(f"{V1}/audit/logs", params={"limit": 200}, headers=auth_header(other_org.token))
    )
    logs_a = ok(
        client.get(f"{V1}/audit/logs", params={"limit": 200}, headers=auth_header(owner_token))
    )
    assert logs_a and logs_b
    ids_a = {r["id"] for r in logs_a}
    assert ids_a.isdisjoint(r["id"] for r in logs_b)
    assert all(r["actor_user_id"] != str(other_org.user_id) for r in logs_a)
    assert a["entry_id"] not in json.dumps(logs_b)
    # Filtrar por entidad o acción de A tampoco muestra lo de A a B.
    entry_logs = ok(
        client.get(
            f"{V1}/audit/logs",
            params={"entity_type": "journal_entry", "limit": 200},
            headers=auth_header(other_org.token),
        )
    )
    assert a["entry_id"] not in json.dumps(entry_logs)
    # La paginación con `before_seq` de un seq de A no revela filas de A.
    top_a = max(r["seq"] for r in logs_a)
    paged = ok(
        client.get(
            f"{V1}/audit/logs",
            params={"before_seq": top_a + 1, "limit": 200},
            headers=auth_header(other_org.token),
        )
    )
    assert ids_a.isdisjoint(r["id"] for r in paged)
    assert b["entry_id"] in json.dumps(logs_b)


def test_security_events_without_organization_are_not_shown(
    client: TestClient, owner_token: str, other_org: OtherOrg, db: Session
) -> None:
    """Un intento con un email desconocido no tiene organización: no se muestra (D-134)."""
    stray = client.post(
        "/api/v1/auth/login", json={"email": "nadie@desconocido.example", "password": "mala"}
    )
    assert stray.status_code == 401
    orphan = db.scalar(
        text(
            "SELECT count(*) FROM audit.security_events"
            " WHERE organization_id IS NULL AND email_attempted = 'nadie@desconocido.example'"
        )
    )
    assert orphan == 1
    for token in (owner_token, other_org.token):
        events = ok(
            client.get(
                f"{V1}/audit/security-events", params={"limit": 200}, headers=auth_header(token)
            )
        )
        assert events, "cada organización ve sus propios eventos"
        assert "nadie@desconocido.example" not in json.dumps(events)
    # Los eventos con organización siguen separados.
    b_events = ok(
        client.get(
            f"{V1}/audit/security-events",
            params={"limit": 200},
            headers=auth_header(other_org.token),
        )
    )
    b_users = {e["user_id"] for e in b_events if e["user_id"]}
    assert b_users <= {str(other_org.user_id)}


def test_verify_endpoints_do_not_reveal_other_organizations(
    client: TestClient, owner_token: str, other_org: OtherOrg, worlds: tuple[World, World]
) -> None:
    """Las verificaciones de cadena no devuelven rutas ni ids de la otra organización."""
    a, _ = worlds
    for path in ("/audit/verify", "/marangatu/verify"):
        res = _call(client, other_org.token, "GET", path)
        assert res.status_code == 200
        _assert_no_leak(res, a, path)


def test_other_org_fixture_logs_in_with_its_own_session(
    client: TestClient, owner_token: str, other_org: OtherOrg
) -> None:
    a = ok(client.get(f"{V1}/auth/me", headers=auth_header(owner_token)))
    b = ok(client.get(f"{V1}/auth/me", headers=auth_header(other_org.token)))
    assert a["organization"]["id"] != b["organization"]["id"]
    assert b["user"]["email"] == other_org.email
    contexts = ok(client.get(f"{FIN}/contexts", headers=auth_header(other_org.token)))
    assert [c["id"] for c in contexts] == [other_org.business_context_id]
