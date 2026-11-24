"""Catálogo de permisos y roles del sistema.

Fuente de verdad del código. La migración 0001 los carga en `core.permissions`,
`core.roles` y `core.role_permissions`; cada módulo nuevo agrega los suyos con una
migración (p. ej. `finance.*` en la 0002, `accounting.*` en la 0003 y `tax.*` en la 0005)
y una prueba verifica que la base y este catálogo coincidan.
"""

from enum import StrEnum


class Perm(StrEnum):
    ORGANIZATION_READ = "organization.read"
    ORGANIZATION_MANAGE = "organization.manage"
    USERS_READ = "users.read"
    USERS_MANAGE = "users.manage"
    AUDIT_READ = "audit.read"
    # Finanzas (fase 2). Aplican al contexto empresarial; el personal es solo de su dueño.
    FINANCE_READ = "finance.read"
    FINANCE_MANAGE = "finance.manage"
    # Contabilidad (fase 3, D-043). El administrador gestiona pero no contabiliza ni cierra.
    ACCOUNTING_READ = "accounting.read"
    ACCOUNTING_MANAGE = "accounting.manage"
    ACCOUNTING_POST = "accounting.post"
    # Tributación (fase 4, D-094). Verificar reglas y el perfil es un acto profesional.
    TAX_READ = "tax.read"
    TAX_MANAGE = "tax.manage"
    TAX_VERIFY = "tax.verify"


PERMISSION_DESCRIPTIONS: dict[Perm, str] = {
    Perm.ORGANIZATION_READ: "Ver los datos de la organización",
    Perm.ORGANIZATION_MANAGE: "Modificar los datos de la organización",
    Perm.USERS_READ: "Ver los usuarios de la organización",
    Perm.USERS_MANAGE: "Crear usuarios, cambiar roles y desactivarlos",
    Perm.AUDIT_READ: "Consultar la auditoría y los eventos de seguridad",
    Perm.FINANCE_READ: "Ver las finanzas de la empresa (cuentas, movimientos y resúmenes)",
    Perm.FINANCE_MANAGE: "Cargar, editar, anular e importar movimientos de la empresa",
    Perm.ACCOUNTING_READ: "Ver la contabilidad: plan de cuentas, asientos y reportes",
    Perm.ACCOUNTING_MANAGE: "Editar el plan de cuentas, preparar borradores de asientos y "
    "asignar cuentas contables en finanzas",
    Perm.ACCOUNTING_POST: "Contabilizar y revertir asientos, cerrar y reabrir períodos, cerrar el "
    "ejercicio y validar el plan de cuentas",
    Perm.TAX_READ: "Ver la tributación: perfil fiscal, reglas, calendario, comprobantes, IVA y "
    "avisos",
    Perm.TAX_MANAGE: "Cargar el perfil declarado, comprobantes, obligaciones, feriados, "
    "excepciones y la configuración tributaria",
    Perm.TAX_VERIFY: "Verificar reglas tributarias y el perfil fiscal, y deprecar reglas",
}


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    ACCOUNTANT = "accountant"
    VIEWER = "viewer"


ROLE_INFO: dict[Role, tuple[str, str]] = {
    Role.OWNER: ("Propietario", "Control total, incluida la gestión de propietarios"),
    Role.ADMIN: ("Administrador", "Administra usuarios y configuración"),
    Role.ACCOUNTANT: ("Contador", "Opera la contabilidad y consulta la auditoría"),
    Role.VIEWER: ("Consulta", "Solo lectura"),
}

ROLE_PERMISSIONS: dict[Role, frozenset[Perm]] = {
    Role.OWNER: frozenset(Perm),
    Role.ADMIN: frozenset(Perm) - {Perm.ACCOUNTING_POST, Perm.TAX_VERIFY},
    Role.ACCOUNTANT: frozenset(
        {
            Perm.ORGANIZATION_READ,
            Perm.USERS_READ,
            Perm.AUDIT_READ,
            Perm.FINANCE_READ,
            Perm.FINANCE_MANAGE,
            Perm.ACCOUNTING_READ,
            Perm.ACCOUNTING_MANAGE,
            Perm.ACCOUNTING_POST,
            Perm.TAX_READ,
            Perm.TAX_MANAGE,
            Perm.TAX_VERIFY,
        }
    ),
    Role.VIEWER: frozenset(
        {Perm.ORGANIZATION_READ, Perm.FINANCE_READ, Perm.ACCOUNTING_READ, Perm.TAX_READ}
    ),
}
