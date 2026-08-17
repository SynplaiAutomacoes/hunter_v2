from django.db import migrations


def backfill_commission_rules_from_legacy_configuration(apps, schema_editor):
    """Migra o legado receives_commission + commission_percentage para regras manuais.

    Colaboradores que recebem comissão e possuem percentual legado, sem regra ativa,
    ganham uma regra de Serviço (percentual, venda bruta, por participação) — o
    comportamento de facto antigo, agora explícito via CollaboratorCommissionRule.
    """
    CollaboratorCommissionRule = apps.get_model("collaborators", "CollaboratorCommissionRule")
    WorkshopCollaborator = apps.get_model("collaborators", "WorkshopCollaborator")

    candidates = (
        WorkshopCollaborator.objects.filter(receives_commission=True, commission_percentage__isnull=False)
        .exclude(commission_rules__is_active=True)
        .order_by("pk")
    )

    created_count = 0
    for collaborator in candidates.iterator():
        percentage = collaborator.commission_percentage
        if percentage is None:
            continue
        CollaboratorCommissionRule.objects.create(
            collaborator=collaborator,
            scope="service",
            modality="percentage",
            apply_scope="participation",
            base="gross_sale",
            percentage=percentage,
            fixed_amount=None,
            is_active=True,
        )
        created_count += 1

    if created_count:
        print(f"[0017] {created_count} regra(s) de comissao migradas de configuracoes legadas.")


class Migration(migrations.Migration):

    dependencies = [
        ("collaborators", "0016_commission_entry_origin"),
    ]

    operations = [
        migrations.RunPython(backfill_commission_rules_from_legacy_configuration, migrations.RunPython.noop),
    ]