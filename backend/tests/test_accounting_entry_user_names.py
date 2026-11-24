"""Nombre visible de quien creó y contabilizó un asiento (P-10).

El rol Consulta no puede leer `/users`; los asientos y el libro diario traen
`created_by_name` y `posted_by_name` (o null), sin ningún otro dato del usuario.
"""

from typing import Any

from fastapi.testclient import TestClient

from tests.accounting_utils import ACC, BANCOS, CAPITAL, create_year, draft, load_chart, post
from tests.conftest import auth_header
from tests.finance_utils import ok

USER_FIELDS = {"created_by", "created_by_name", "posted_by", "posted_by_name", "discarded_by"}


def test_entries_and_journal_show_user_names_only(
    client: TestClient, owner_token: str, make_user: Any
) -> None:
    accounts = load_chart(client, owner_token)
    create_year(client, owner_token, 2026)
    _, accountant = make_user("accountant")
    _, viewer = make_user("viewer")
    lines = [(BANCOS, 1000, 0), (CAPITAL, 0, 1000)]
    pending = draft(client, owner_token, accounts, "2026-02-01", lines, "Queda en borrador")
    done = draft(client, owner_token, accounts, "2026-02-02", lines, "Se contabiliza")
    ok(post(client, accountant, done["id"]))

    headers = auth_header(viewer)
    assert client.get("/api/v1/users", headers=headers).status_code == 403
    posted_entry = ok(client.get(f"{ACC}/entries/{done['id']}", headers=headers))
    assert posted_entry["created_by_name"] == "Dueña de Prueba"
    assert posted_entry["posted_by_name"] == "Usuario accountant"
    draft_entry = ok(client.get(f"{ACC}/entries/{pending['id']}", headers=headers))
    assert draft_entry["created_by_name"] == "Dueña de Prueba"
    assert draft_entry["posted_by_name"] is None
    listed = ok(client.get(f"{ACC}/entries", headers=headers))
    assert {e["id"]: e["posted_by_name"] for e in listed} == {
        pending["id"]: None,
        done["id"]: "Usuario accountant",
    }
    journal = ok(
        client.get(
            f"{ACC}/reports/journal",
            params={"from": "2026-01-01", "to": "2026-12-31"},
            headers=headers,
        )
    )
    [entry] = journal["entries"]
    assert (entry["created_by_name"], entry["posted_by_name"]) == (
        "Dueña de Prueba",
        "Usuario accountant",
    )
    # Nada más del usuario: ni correo, ni rol, ni ningún otro campo nuevo.
    text = str(posted_entry)
    assert "example.com" not in text and "accountant@" not in text
    assert {k for k in posted_entry if k.endswith(("_by", "_by_name"))} == USER_FIELDS
