# Generated for Commission v3 — Pool + Limites por Workshop
from decimal import Decimal
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models
import django.db.models.deletion
import djmoney.models.fields


def migrate_legacy_commission_percentage(apps, schema_editor):
    WorkshopCollaborator = apps.get_model("collaborators", "WorkshopCollaborator")
    CollaboratorCommissionRule = apps.get_model("collaborators", "CollaboratorCommissionRule")
    for collab in WorkshopCollaborator.objects.filter(receives_commission=True, commission_percentage__isnull=False).iterator():
        pct = collab.commission_percentage
        if pct is None:
            continue
        try:
            pct_dec = Decimal(str(pct))
        except Exception:
            continue
        if pct_dec <= 0:
            continue
        # Criar regra de serviço por participação — resposta #9
        CollaboratorCommissionRule.objects.get_or_create(
            collaborator_id=collab.pk,
            scope="service",
            defaults={
                "modality": "percentage",
                "apply_scope": "participation",
                "percentage": pct_dec,
                "is_active": True,
            },
        )


def reverse_migrate_legacy(apps, schema_editor):
    # Reversão estreita: apagar apenas regras que coincidem exatamente com o valor legado,
    # para não destruir regras criadas manualmente via UI após a migração.
    WorkshopCollaborator = apps.get_model("collaborators", "WorkshopCollaborator")
    CollaboratorCommissionRule = apps.get_model("collaborators", "CollaboratorCommissionRule")
    for collab in WorkshopCollaborator.objects.filter(receives_commission=True, commission_percentage__isnull=False).iterator():
        try:
            pct = Decimal(str(collab.commission_percentage))
        except Exception:
            continue
        CollaboratorCommissionRule.objects.filter(
            collaborator_id=collab.pk,
            scope="service",
            apply_scope="participation",
            modality="percentage",
            percentage=pct,
            is_active=True,
        ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('collaborators', '0017_backfill_payroll_commission_titles'),
        ('workorder', '0047_workorder_courtesy_reason_fields'),
        ('workshops', '0045_add_workshop_commission_limits'),
    ]

    operations = [
        migrations.CreateModel(
            name='CollaboratorCommissionRule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('scope', models.CharField(choices=[('service', 'Serviço'), ('product', 'Produto')], max_length=10, verbose_name='Escopo')),
                ('modality', models.CharField(choices=[('percentage', 'Percentual (%)'), ('fixed', 'Valor Fixo (R$)')], max_length=12, verbose_name='Modalidade')),
                ('apply_scope', models.CharField(choices=[('participation', 'Por Participação'), ('global', 'Global')], default='participation', max_length=14, verbose_name='Aplicação')),
                ('percentage', models.DecimalField(blank=True, decimal_places=6, max_digits=7, null=True, validators=[MinValueValidator(0), MaxValueValidator(1)], verbose_name='Percentual de Comissão')),
                ('fixed_amount', djmoney.models.fields.MoneyField(blank=True, decimal_places=2, max_digits=14, null=True, verbose_name='Valor Fixo')),
                ('fixed_amount_currency', djmoney.models.fields.CurrencyField(choices=[('BRL', 'Brazilian Real')], default='BRL', editable=False, max_length=3)),
                ('is_active', models.BooleanField(default=True, verbose_name='Ativa')),
                ('collaborator', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='commission_rules', to='collaborators.workshopcollaborator')),
            ],
            options={
                'verbose_name': 'Regra de Comissão do Colaborador',
                'verbose_name_plural': 'Regras de Comissão do Colaborador',
            },
        ),
        migrations.AddConstraint(
            model_name='collaboratorcommissionrule',
            constraint=models.UniqueConstraint(condition=models.Q(('is_active', True)), fields=('collaborator', 'scope'), name='unique_active_commission_rule_per_collaborator_scope'),
        ),
        migrations.CreateModel(
            name='WorkOrderCommissionAllocation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('scope', models.CharField(choices=[('service', 'Serviço'), ('product', 'Produto')], max_length=10, verbose_name='Escopo')),
                ('distribution_percentage', models.DecimalField(default=Decimal('0'), help_text='Percentual da distribuição do pool para este colaborador no escopo.', max_digits=7, decimal_places=6, validators=[MinValueValidator(0), MaxValueValidator(1)], verbose_name='Base (%)')),
                ('collaborator', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='commission_allocations', to='collaborators.workshopcollaborator')),
                ('workorder', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='commission_allocations', to='workorder.workorder')),
            ],
            options={
                'verbose_name': 'Alocação de Comissão da O.S.',
                'verbose_name_plural': 'Alocações de Comissão da O.S.',
            },
        ),
        migrations.AddConstraint(
            model_name='workordercommissionallocation',
            constraint=models.UniqueConstraint(fields=('workorder', 'collaborator', 'scope'), name='unique_workorder_commission_allocation'),
        ),
        migrations.AddConstraint(
            model_name='workordercommissionallocation',
            constraint=models.CheckConstraint(condition=models.Q(distribution_percentage__gte=0, distribution_percentage__lte=1), name='workorder_allocation_distribution_percentage_range'),
        ),
        # Alter CollaboratorCommissionEntry — add v3 fields
        migrations.AddField(
            model_name='collaboratorcommissionentry',
            name='commission_origin',
            field=models.CharField(blank=True, choices=[('service_pct_pool', 'Serviço % (Pool)'), ('service_fixed', 'Serviço Fixo'), ('product_pct_pool', 'Produto % (Pool)'), ('product_fixed', 'Produto Fixo'), ('service_global', 'Serviço Global'), ('product_global', 'Produto Global'), ('workorder_rate', 'Comissão por OS (Oficina)'), ('service_rule', 'Regra de Serviço'), ('product_rule', 'Regra de Produto')], help_text='Escopo + modalidade + aplicação da comissão no pool.', max_length=32, null=True, verbose_name='Origem da Comissão (v3)'),
        ),
        migrations.AddField(
            model_name='collaboratorcommissionentry',
            name='commission_rule',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='commission_entries', to='collaborators.collaboratorcommissionrule'),
        ),
        migrations.AddField(
            model_name='collaboratorcommissionentry',
            name='is_fixed_amount',
            field=models.BooleanField(default=False, verbose_name='Valor Fixo'),
        ),
        migrations.AddField(
            model_name='collaboratorcommissionentry',
            name='distribution_percentage',
            field=models.DecimalField(default=Decimal('0'), max_digits=7, decimal_places=6, validators=[MinValueValidator(0), MaxValueValidator(1)], verbose_name='Base (%) snapshot'),
        ),
        migrations.AddField(
            model_name='collaboratorcommissionentry',
            name='pool_amount',
            field=djmoney.models.fields.MoneyField(decimal_places=2, default=Decimal('0.00'), max_digits=14, verbose_name='Valor do Pool'),
        ),
        migrations.AddField(
            model_name='collaboratorcommissionentry',
            name='pool_amount_currency',
            field=djmoney.models.fields.CurrencyField(choices=[('BRL', 'Brazilian Real')], default='BRL', editable=False, max_length=3),
        ),
        migrations.RemoveConstraint(
            model_name='collaboratorcommissionentry',
            name='unique_collaborator_commission_workorder',
        ),
        migrations.AddConstraint(
            model_name='collaboratorcommissionentry',
            constraint=models.UniqueConstraint(fields=('collaborator', 'workorder', 'commission_origin'), name='unique_collaborator_commission_per_origin'),
        ),
        migrations.AddIndex(
            model_name='collaboratorcommissionentry',
            index=models.Index(fields=['workorder', 'commission_origin'], name='collab_comm_wo_origin_idx'),
        ),
        migrations.RunPython(migrate_legacy_commission_percentage, reverse_migrate_legacy),
    ]
