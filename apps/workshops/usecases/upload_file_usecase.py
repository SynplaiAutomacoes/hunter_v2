from __future__ import annotations

from django.core.files.uploadedfile import UploadedFile

from apps.finance.models.finance import WebmaniaCompany
from apps.workshops.models.workshops import Workshop
from apps.workshops.services.files import (
    build_workshop_logo_public_url,
    clear_workshop_logo_atomic,
    save_workshop_certificate_atomic,
    save_workshop_logo_atomic,
)


class UploadWorkshopFileUseCase:
    def __init__(self, *, request=None) -> None:
        self.request = request

    def upload_logo(self, *, workshop: Workshop, company: WebmaniaCompany, uploaded_file: UploadedFile) -> str:
        return save_workshop_logo_atomic(
            workshop=workshop,
            company=company,
            uploaded_file=uploaded_file,
            request=self.request,
        )

    def clear_logo(self, *, workshop: Workshop, company: WebmaniaCompany) -> None:
        clear_workshop_logo_atomic(
            workshop=workshop,
            company=company,
            request=self.request,
        )

    def upload_certificate(
        self,
        *,
        workshop: Workshop,
        company: WebmaniaCompany,
        uploaded_file: UploadedFile | None,
        certificate_password: str,
    ) -> None:
        save_workshop_certificate_atomic(
            workshop=workshop,
            company=company,
            uploaded_file=uploaded_file,
            certificate_password=certificate_password,
        )

    def logo_public_url(self, *, workshop: Workshop) -> str:
        return build_workshop_logo_public_url(workshop=workshop, request=self.request)
