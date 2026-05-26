import re

from django.core.exceptions import ValidationError
from django.db.models import CharField
from django.utils.translation import gettext_lazy as _

from localflavor.br.validators import (
    BRCPFValidator,
    BRCNPJValidator,
)


class BRCPFCNPJField(CharField):
    description = _("CPF or CNPJ document")

    default_error_messages = {
        "invalid": _("Informe um CPF ou CNPJ válido."),
    }

    def __init__(self, *args, **kwargs):
        kwargs["max_length"] = 18
        super().__init__(*args, **kwargs)

        self.cpf_validator = BRCPFValidator()
        self.cnpj_validator = BRCNPJValidator()

    def clean(self, value, model_instance):
        value = super().clean(value, model_instance)

        if not value:
            return value

        numbers = re.sub(r"\D", "", value)

        try:
            if len(numbers) == 11:
                self.cpf_validator(value)
            elif len(numbers) == 14:
                self.cnpj_validator(value)
            else:
                raise ValidationError(self.error_messages["invalid"])
        except ValidationError:
            raise ValidationError(self.error_messages["invalid"])

        return value