from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.terms.defaults import default_vehicle_receipt_content, default_warranty_content
from apps.terms.models import TermTemplateType, WorkshopTermTemplate
from apps.workshops.models.workshops import Workshop


class Command(BaseCommand):
    help = "Cria termos padrão de recebimento e garantia para oficinas sem cadastro."

    def handle(self, *args, **options):
        created_count = 0
        for workshop in Workshop.objects.all().iterator():
            if not WorkshopTermTemplate.objects.filter(workshop=workshop, template_type=TermTemplateType.VEHICLE_RECEIPT).exists():
                WorkshopTermTemplate.objects.create(
                    workshop=workshop,
                    template_type=TermTemplateType.VEHICLE_RECEIPT,
                    name="Recebimento padrão",
                    document_title="TERMO DE RECEBIMENTO DE VEÍCULO",
                    subtitle="Informações importantes para diagnóstico e manutenção",
                    intro_text="Prezado Cliente, para que possamos dar andamento no diagnóstico ou manutenção do seu veículo, apresentamos abaixo informações importantes sobre o atendimento.",
                    is_default=True,
                    content=default_vehicle_receipt_content(),
                )
                created_count += 1

            if not WorkshopTermTemplate.objects.filter(workshop=workshop, template_type=TermTemplateType.WARRANTY).exists():
                WorkshopTermTemplate.objects.create(
                    workshop=workshop,
                    template_type=TermTemplateType.WARRANTY,
                    name="Garantia padrão",
                    document_title="TERMO DE GARANTIA",
                    subtitle="Condições de cobertura dos serviços executados",
                    is_default=True,
                    content=default_warranty_content(),
                )
                created_count += 1

        self.stdout.write(self.style.SUCCESS(f"Termos padrão verificados. Novos registros criados: {created_count}"))
