from django.db import migrations, models

from apps.finance.migrations import _idempotent


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0058_repair_purchase_return_item_columns"),
    ]

    operations = [
        _idempotent.AddFieldIfMissing(
            model_name="purchasereturnrequest",
            name="fisco_information",
            field=models.TextField(blank=True, default="", verbose_name="Informações ao fisco"),
        ),
        _idempotent.AddFieldIfMissing(
            model_name="purchasereturnrequest",
            name="volume",
            field=models.PositiveBigIntegerField(blank=True, null=True, verbose_name="Quantidade de volumes"),
        ),
        _idempotent.AddFieldIfMissing(
            model_name="purchasereturnrequest",
            name="freight_mode",
            field=models.PositiveSmallIntegerField(
                choices=[
                    (0, "Por conta do emitente (CIF)"),
                    (1, "Por conta do destinatario (FOB)"),
                    (2, "Por conta de terceiros"),
                    (3, "Transporte proprio do emitente"),
                    (4, "Transporte proprio do destinatario"),
                    (9, "Sem transporte"),
                ],
                default=9,
                verbose_name="Modalidade de frete",
            ),
        ),
        _idempotent.AddFieldIfMissing(
            model_name="purchasereturnrequest",
            name="freight_amount",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=15, null=True, verbose_name="Frete"),
        ),
        _idempotent.AddFieldIfMissing(
            model_name="purchasereturnrequest",
            name="discount_amount",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=15, null=True, verbose_name="Desconto"),
        ),
        _idempotent.AddFieldIfMissing(
            model_name="purchasereturnrequest",
            name="accessory_expenses",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=15, null=True, verbose_name="Despesas acessórias"),
        ),
        _idempotent.AddFieldIfMissing(
            model_name="purchasereturnrequest",
            name="insurance_amount",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=15, null=True, verbose_name="Seguro"),
        ),
        _idempotent.AddFieldIfMissing(
            model_name="purchasereturnrequest",
            name="customs_expenses",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=15, null=True, verbose_name="Despesas aduaneiras"),
        ),
        _idempotent.AddFieldIfMissing(
            model_name="purchasereturnrequest",
            name="total_override",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=15, null=True, verbose_name="Total informado"),
        ),
        _idempotent.AddFieldIfMissing(
            model_name="purchasereturnrequest",
            name="presence",
            field=models.CharField(blank=True, default="", max_length=1, verbose_name="Indicador de presença"),
        ),
        _idempotent.AddFieldIfMissing(
            model_name="purchasereturnrequest",
            name="intermediary",
            field=models.CharField(blank=True, default="", max_length=1, verbose_name="Indicador de intermediador"),
        ),
        _idempotent.AddFieldIfMissing(
            model_name="purchasereturnrequest",
            name="intermediary_cnpj",
            field=models.CharField(blank=True, default="", max_length=14, verbose_name="CNPJ do intermediador"),
        ),
        _idempotent.AddFieldIfMissing(
            model_name="purchasereturnrequest",
            name="intermediary_id",
            field=models.CharField(blank=True, default="", max_length=60, verbose_name="Identificador do intermediador"),
        ),
        _idempotent.AddFieldIfMissing(
            model_name="purchasereturnrequest",
            name="purchase_order",
            field=models.CharField(blank=True, default="", max_length=60, verbose_name="Pedido de compra"),
        ),
        _idempotent.AddFieldIfMissing(
            model_name="purchasereturnrequest",
            name="contract",
            field=models.CharField(blank=True, default="", max_length=60, verbose_name="Contrato"),
        ),
        _idempotent.AddFieldIfMissing(
            model_name="purchasereturnrequest",
            name="commitment_note",
            field=models.CharField(blank=True, default="", max_length=22, verbose_name="Nota de empenho"),
        ),
        _idempotent.AddFieldIfMissing(
            model_name="purchasereturnrequest",
            name="payment_indicator",
            field=models.CharField(blank=True, default="", max_length=1, verbose_name="Indicador de pagamento"),
        ),
        _idempotent.AddFieldIfMissing(
            model_name="purchasereturnrequest",
            name="payment_method",
            field=models.CharField(blank=True, default="", max_length=2, verbose_name="Meio de pagamento"),
        ),
        _idempotent.AddFieldIfMissing(
            model_name="purchasereturnrequest",
            name="payment_description",
            field=models.CharField(blank=True, default="", max_length=60, verbose_name="Descrição do pagamento"),
        ),
        _idempotent.AddFieldIfMissing(
            model_name="purchasereturnrequest",
            name="payment_value",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=15, null=True, verbose_name="Valor do pagamento"),
        ),
        _idempotent.AddFieldIfMissing(
            model_name="purchasereturnrequest",
            name="payment_date",
            field=models.DateField(blank=True, null=True, verbose_name="Data do pagamento"),
        ),
        _idempotent.AddFieldIfMissing(
            model_name="purchasereturnrequest",
            name="issue_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Data de emissão"),
        ),
        _idempotent.AddFieldIfMissing(
            model_name="purchasereturnrequest",
            name="departure_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Data de entrada/saída"),
        ),
        _idempotent.AddFieldIfMissing(
            model_name="purchasereturnrequest",
            name="delivery_forecast",
            field=models.DateField(blank=True, null=True, verbose_name="Previsão de entrega"),
        ),
        _idempotent.AddFieldIfMissing(
            model_name="purchasereturnrequest",
            name="transport_snapshot",
            field=models.JSONField(blank=True, default=dict, verbose_name="Snapshot de transporte"),
        ),
    ]
