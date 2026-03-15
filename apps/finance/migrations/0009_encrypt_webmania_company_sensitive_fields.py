import base64
import hashlib

from cryptography.fernet import Fernet
from django.db import migrations


_ENCRYPTED_PREFIX = "enc::"


def _build_fernet_key() -> bytes:
    from django.conf import settings

    secret_key = str(getattr(settings, "SECRET_KEY", "") or "").encode()
    digest = hashlib.sha256(secret_key).digest()
    return base64.urlsafe_b64encode(digest)


def _encrypt_if_needed(value: object) -> str:
    raw_value = str(value or "")
    if not raw_value:
        return ""
    if raw_value.startswith(_ENCRYPTED_PREFIX):
        return raw_value

    fernet = Fernet(_build_fernet_key())
    encrypted = fernet.encrypt(raw_value.encode()).decode()
    return f"{_ENCRYPTED_PREFIX}{encrypted}"


def _encrypt_existing_company_secrets(apps, schema_editor):
    WebmaniaCompany = apps.get_model("finance", "WebmaniaCompany")
    fields_to_encrypt = (
        "consumer_key",
        "consumer_secret",
        "access_token",
        "access_token_secret",
        "bearer_access_token",
        "nfse_password",
        "nfse_token",
        "certificado",
        "certificado_senha",
    )

    for company in WebmaniaCompany.objects.all().iterator():
        has_changes = False
        for field_name in fields_to_encrypt:
            current_value = getattr(company, field_name)
            encrypted_value = _encrypt_if_needed(current_value)
            if encrypted_value != current_value:
                setattr(company, field_name, encrypted_value)
                has_changes = True

        if has_changes:
            company.save(update_fields=list(fields_to_encrypt))


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0008_alter_webmaniacompany_tipo_tributacao"),
    ]

    operations = [
        migrations.RunPython(_encrypt_existing_company_secrets, migrations.RunPython.noop),
    ]
