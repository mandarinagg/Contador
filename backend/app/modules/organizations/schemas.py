"""Identidad de una organización al darla de alta: empresa o persona física (D-141)."""

from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints, model_validator

LegalForm = Literal["EAS", "SA", "SRL", "UNIPERSONAL", "PERSONA_FISICA", "OTRA"]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=200)]
PersonName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class OrganizationIdentity(BaseModel):
    """Una empresa lleva razón social; una persona física, nombres y apellidos (y su razón
    social se calcula como «Apellidos, Nombres»)."""

    legal_name: Name | None = None
    trade_name: Name | None = None
    legal_form: LegalForm = "EAS"
    first_names: PersonName | None = None
    last_names: PersonName | None = None

    @model_validator(mode="after")
    def _identity(self) -> "OrganizationIdentity":
        if self.legal_form == "PERSONA_FISICA":
            if self.first_names is None or self.last_names is None:
                raise ValueError("Una persona física lleva nombres y apellidos.")
            if self.legal_name is not None:
                raise ValueError("La razón social de una persona física se calcula de su nombre.")
        else:
            if self.first_names is not None or self.last_names is not None:
                raise ValueError("Los nombres y apellidos son solo de una persona física.")
            if self.legal_name is None:
                raise ValueError("Falta la razón social.")
        return self
