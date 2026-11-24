"""Catálogo de permisos y roles del sistema.

Fuente de verdad del código. La migración 0001 los carga en `core.permissions`,
`core.roles` y `core.role_permissions`; cada módulo nuevo agrega los suyos con una
migración y una prueba verifica que la base y este catálogo coincidan.
"""

from enum import StrEnum


class Perm(StrEnum):
    ORGANIZATION_READ = "organization.read"
    ORGANIZATION_MANAGE = "organization.manage"
    USERS_READ = "users.read"
    USERS_MANAGE = "users.manage"
    AUDIT_READ = "audit.read"


PERMISSION_DESCRIPTIONS: dict[Perm, str] = {
    Perm.ORGANIZATION_READ: "Ver los datos de la organización",
    Perm.ORGANIZATION_MANAGE: "Modificar los datos de la organización",
    Perm.USERS_READ: "Ver los usuarios de la organización",
    Perm.USERS_MANAGE: "Crear usuarios, cambiar roles y desactivarlos",
    Perm.AUDIT_READ: "Consultar la auditoría y los eventos de seguridad",
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
    Role.ADMIN: frozenset(Perm),
    Role.ACCOUNTANT: frozenset({Perm.ORGANIZATION_READ, Perm.USERS_READ, Perm.AUDIT_READ}),
    Role.VIEWER: frozenset({Perm.ORGANIZATION_READ}),
}
