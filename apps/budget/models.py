from datetime import timedelta
from typing import Any

from django.db import models, transaction
from django.core.validators import MinValueValidator, MaxValueValidator
from django.conf import settings
from djmoney.money import Money

from apps.catalog.models.kits import Kit
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.core.models import TimeStampedModel
from djmoney.models.fields import MoneyField

from apps.workorder.models import WorkOrder

from apps.workshops.models.monthly_costs import MonthlyCost
from apps.workshops.models.workshop_costs import WorkshopCost, WorkshopCostItem
from django.utils import timezone
from decimal import Decimal, ROUND_HALF_UP


class BudgetStatus(models.TextChoices):
    DRAFT = "draft", "Em Aberto"
    WAITING_CLIENT = "waiting_client", "Aguardando Relato do Cliente"
    WAITING_DIAGNOSIS = "waiting_diagnosis", "Aguardando Diagnóstico"
    WAITING_ITEMS = "waiting_items", "Aguardando Itens"
    WAITING_PRICING = "waiting_pricing", "Aguardando Precificação"
    WAITING_REVIEW = "waiting_review", "Aguardando Revisão"
    APPROVED = "approved", "Aprovado"
    REJECTED = "rejected", "Rejeitado"
    CANCELLED = "cancelled", "Cancelado"


class FuelLevel(models.IntegerChoices):
    FULL = 8, "Cheio"
    SEVEN_EIGHTHS = 7, "7/8"
    THREE_QUARTERS = 6, "3/4"
    ONE_HALF = 5, "1/2"
    ONE_QUARTER = 4, "1/4"
    ONE_EIGHTH = 3, "1/8"
    RESERVE = 2, "Reserva"
    EMPTY = 1, "Vazio"


class Defect(models.Model):
    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="defects")
    budget = models.ForeignKey("budget.Budget", on_delete=models.CASCADE, related_name="defects")
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Defeito"
        verbose_name_plural = "Defeitos"
        constraints = [models.UniqueConstraint(fields=("budget", "name"), name="unique_budget_name_per_defetct")]

    def __str__(self):
        return self.name


class Budget(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE, related_name="budgets")
    customer = models.ForeignKey("customer.Customer", verbose_name="Cliente", on_delete=models.SET_NULL, related_name="budgets", null=True)
    vehicle = models.ForeignKey("customer.Vehicle", verbose_name="Veículo", on_delete=models.SET_NULL, related_name="budgets", null=True)
    cost_estimator = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="Orçamentista", on_delete=models.SET_NULL, related_name="budgets", null=True)
    collaborator = models.ForeignKey("collaborators.WorkshopCollaborator", verbose_name="Colaborador", on_delete=models.SET_NULL, related_name="budgets", null=True)

    # Datas e Prazos
    expiration_date = models.DateField(verbose_name="Data de Validade", null=True, blank=True)
    entry_date = models.DateField(verbose_name="Data de Entrada")

    # Informações Técnicas
    problem_description = models.TextField(verbose_name="Relato principal do cliente", blank=True, null=True)
    technical_diagnosis = models.TextField(verbose_name="Observações Técnicas", blank=True, null=True)
    notes = models.TextField(verbose_name="Observações Complementares", blank=True, null=True)
    current_km = models.PositiveIntegerField(verbose_name="KM Atual", default=0)
    fuel_level = models.PositiveIntegerField(verbose_name="Nível do Tanque", choices=FuelLevel.choices, default=FuelLevel.FULL)
    defect = models.ForeignKey(Defect, on_delete=models.SET_NULL, related_name="budgets", null=True)

    # Financeiro
    discount_value = MoneyField(verbose_name="Aplicar Desconto (R$)", max_digits=14, decimal_places=2, default=0.00)

    # Margens e Ajustes
    profit_margin_parts = models.DecimalField(verbose_name="Percentual Lucro de Peças", max_digits=5, decimal_places=2, default=0.00)
    profit_margin_labor = models.DecimalField(verbose_name="Percentual Lucro de Mão de Obra", max_digits=5, decimal_places=2, default=0.00)
    slider = models.SmallIntegerField(verbose_name="Slider", default=0, validators=[MinValueValidator(-100), MaxValueValidator(100)], help_text="Negativo: Peça | Positivo: Mão de Obra")

    # Status e Controle
    status = models.CharField(verbose_name="Status", max_length=20, choices=BudgetStatus.choices, default=BudgetStatus.DRAFT)
    cancellation_reason = models.CharField(verbose_name="Motivo do Cancelamento", max_length=255, blank=True, null=True)
    current_step = models.PositiveSmallIntegerField(verbose_name="Etapa Atual", default=1)

    def save(self, *args, **kwargs):
        is_new = self.pk is None

        old_status = None
        if not is_new:
            old_status = Budget.objects.filter(pk=self.pk).values_list("status", flat=True).first()

        with transaction.atomic():
            super().save(*args, **kwargs)

            if old_status != BudgetStatus.APPROVED and self.status == BudgetStatus.APPROVED:
                WorkOrder.objects.get_or_create(
                    budget=self,
                    defaults={"workshop": self.workshop},
                )

        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Orçamento"
        verbose_name_plural = "Orçamentos"

    def calculate_pricing_methods(self):
        try:
            reference_date = self.criado_em if self.criado_em else timezone.now()
            workshop_cost = WorkshopCost.objects.get(workshop=self.workshop, month=reference_date.month, year=reference_date.year)
        except WorkshopCost.DoesNotExist:
            try:
                workshop_cost = WorkshopCost.objects.get(workshop=self.workshop, month=timezone.now().month, year=timezone.now().year)
            except WorkshopCost.DoesNotExist:
                return None

        try:
            mechanic_salary_obj = MonthlyCost.objects.get(workshop=self.workshop, name__iexact="Salários mecânicos produtivos")
            salario_mecanicos = WorkshopCostItem.objects.get(workshop_cost=workshop_cost, monthly_cost=mechanic_salary_obj).amount
        except (WorkshopCost.DoesNotExist, MonthlyCost.DoesNotExist, WorkshopCostItem.DoesNotExist):
            return {
                "valor_orcamento": self.total_products_value + self.total_services_value,
                "rentabilidade": Decimal("0.00"),
            }

        # Índices
        mlr = workshop_cost.profitability_multiplier
        duracao_total = Decimal(self.total_duration.total_seconds()) / Decimal(3600)
        horas_uteis_mes = workshop_cost.working_hours_per_month

        if not horas_uteis_mes or horas_uteis_mes == 0:
            return {
                "valor_orcamento": self.total_products_value + self.total_services_value,
                "rentabilidade": Decimal("0.00"),
            }

        # Custos
        custo_pecas = self.total_costs_products_value
        custo_frete_pecas = self.total_products_shipping
        custo_servico_terceiro = self.total_third_party_services_cost
        custo_hora_mecanico = salario_mecanicos / horas_uteis_mes
        custo_total_mao_obra = duracao_total * custo_hora_mecanico

        # Valores de Venda
        venda_pecas = self.total_products_value - custo_frete_pecas
        venda_servico_terceiro = self.total_third_party_services_selling

        divisor_mlo = (custo_pecas + custo_frete_pecas + custo_servico_terceiro + custo_total_mao_obra).amount
        soma_base_orcamento = venda_pecas + custo_frete_pecas + venda_servico_terceiro
        subtracao_base_lucro = custo_pecas + custo_frete_pecas + custo_total_mao_obra + custo_servico_terceiro

        # MÉTOD0 TRADICIONAL
        valor_hora_vendida_trad = workshop_cost.hourly_cost_value
        venda_mao_obra_trad = valor_hora_vendida_trad * duracao_total
        valor_orcamento_trad = soma_base_orcamento + venda_mao_obra_trad
        lucro_operacional_trad = valor_orcamento_trad - subtracao_base_lucro
        if valor_orcamento_trad.amount > 0:
            rentabilidade_trad = ((lucro_operacional_trad.amount / valor_orcamento_trad.amount) * 100).quantize(Decimal("0.01"), ROUND_HALF_UP)
        else:
            rentabilidade_trad = Decimal("0.00")

        # MÉTOD0 HUNTER
        venda_mao_obra_hun = self.total_services_value - venda_servico_terceiro
        valor_orcamento_hun = soma_base_orcamento + venda_mao_obra_hun
        mlo = valor_orcamento_hun.amount / divisor_mlo if divisor_mlo > 0 else 0
        lucro_operacional_hun = valor_orcamento_hun - subtracao_base_lucro
        if valor_orcamento_hun.amount > 0:
            rentabilidade_hun = ((lucro_operacional_hun.amount / valor_orcamento_hun.amount) * 100).quantize(Decimal("0.01"), ROUND_HALF_UP)
        else:
            rentabilidade_hun = Decimal("0.00")

        # Organização dos dados
        data_trad = {
            "method_name": "Tradicional",
            "custo_pecas": custo_pecas,
            "custo_frete_pecas": custo_frete_pecas,
            "custo_servico_terceiro": custo_servico_terceiro,
            "custo_hora_mecanico": custo_hora_mecanico,
            "custo_total_mao_obra": custo_total_mao_obra,
            "duracao_total": self.total_duration_display,
            "lucro_operacional": lucro_operacional_trad,
            "venda_pecas": venda_pecas,
            "venda_servico_terceiro": venda_servico_terceiro,
            "venda_mao_obra": venda_mao_obra_trad,
            "rentabilidade": rentabilidade_trad,
            "valor_orcamento": valor_orcamento_trad,
        }

        data_hun = {
            "method_name": "Hunter",
            "custo_pecas": custo_pecas,
            "custo_frete_pecas": custo_frete_pecas,
            "custo_servico_terceiro": custo_servico_terceiro,
            "custo_hora_mecanico": custo_hora_mecanico,
            "custo_total_mao_obra": custo_total_mao_obra,
            "duracao_total": self.total_duration_display,
            "lucro_operacional": lucro_operacional_hun,
            "mlr": mlr,
            "venda_pecas": venda_pecas,
            "venda_servico_terceiro": venda_servico_terceiro,
            "venda_mao_obra": venda_mao_obra_hun,
            "rentabilidade": rentabilidade_hun,
            "mlo": mlo,
            "valor_orcamento": valor_orcamento_hun,
        }

        return data_trad if rentabilidade_trad > rentabilidade_hun else data_hun

    @property
    def total_duration_display(self) -> str:
        total_td = self.total_duration
        if not total_td:
            return "00h 00m"

        ts = int(total_td.total_seconds())
        return f"{ts // 3600:02d}h {(ts % 3600) // 60:02d}m"

    @property
    def budget_status(self):
        return BudgetStatus(self.status).label

    @property
    def collaborator_name(self):
        return self.collaborator.name if self.collaborator else "Sistema"

    @property
    def rentability(self) -> Money:
        data = self.calculate_pricing_methods()
        return data["rentabilidade"]

    def _is_local_product_item(self, item: "BudgetItem") -> bool:
        return item.is_local and ((item.product_cost_price and item.product_cost_price.amount > 0) or (item.product_selling_price and item.product_selling_price.amount > 0) or (item.shipping and item.shipping.amount > 0))

    def _is_local_service_item(self, item: "BudgetItem") -> bool:
        return item.is_local and ((item.service_cost_price and item.service_cost_price.amount > 0) or (item.service_selling_price and item.service_selling_price.amount > 0) or item.duration)

    ## Products
    @property
    def total_products_shipping(self) -> Money:
        total = Money(0, "BRL")
        for item in self.items.all():
            if item.product or self._is_local_product_item(item):
                total += item.shipping
            elif item.kit:
                total += item.get_kit_products_shipping_total()
        return total

    @property
    def total_costs_products_value(self) -> Money:
        total = Money(0, "BRL")
        for item in self.items.all():
            if item.product or self._is_local_product_item(item):
                total += item.product_cost_price * item.quantity
            elif item.kit:
                total += item.get_kit_products_cost_total()
        return total

    @property
    def total_products_value(self) -> Money:
        total = Money(0, "BRL")
        for item in self.items.all():
            if item.product or self._is_local_product_item(item):
                total += (item.product_selling_price * item.quantity) + item.shipping
            elif item.kit:
                total += item.get_kit_products_total()
        return total

    ## Services
    @property
    def total_duration(self) -> timedelta:
        total = timedelta(0)
        for item in self.items.all():
            if (item.service or self._is_local_service_item(item)) and item.duration:
                total += item.duration * item.quantity
            elif item.kit:
                total += item.get_kit_services_duration()
        return total

    @property
    def total_third_party_services_cost(self) -> Money:
        total = Money(0, "BRL")
        for item in self.items.all():
            if item.service and item.service.is_third_party:
                total += item.service_cost_price * item.quantity
            elif item.kit:
                total += item.get_kit_third_party_services_cost_total()
        return total

    @property
    def total_third_party_services_selling(self) -> Money:
        total = Money(0, "BRL")
        for item in self.items.all():
            if item.service and item.service.is_third_party:
                total += item.service_selling_price * item.quantity
            elif item.kit:
                total += item.get_kit_third_party_services_selling_total()
        return total

    @property
    def total_costs_services_value(self) -> Money:
        total = Money(0, "BRL")
        for item in self.items.all():
            if item.service or self._is_local_service_item(item):
                total += item.service_cost_price * item.quantity
            elif item.kit:
                total += item.get_kit_services_cost_total()
        return total

    @property
    def total_services_value(self) -> Money:
        total = Money(0, "BRL")
        for item in self.items.all():
            if item.service or self._is_local_service_item(item):
                total += item.service_selling_price * item.quantity
            elif item.kit:
                total += item.get_kit_services_total()
        return total

    @property
    def budget_status_badge(self):
        status_color = {
            BudgetStatus.DRAFT: "badge-soft badge-ghost",
            BudgetStatus.WAITING_CLIENT: "badge-soft badge-warning",
            BudgetStatus.WAITING_DIAGNOSIS: "badge-soft badge-warning",
            BudgetStatus.WAITING_ITEMS: "badge-soft badge-warning",
            BudgetStatus.WAITING_PRICING: "badge-soft badge-info",
            BudgetStatus.WAITING_REVIEW: "badge-soft badge-info",
            BudgetStatus.APPROVED: "badge-success",
            BudgetStatus.REJECTED: "badge-error",
            BudgetStatus.CANCELLED: "badge-soft badge-error",
        }

        return {"text": BudgetStatus(self.status).label, "class": status_color.get(self.status, "badge-ghost")}

    ## Total
    @property
    def total_base_value(self) -> Money:
        data = self.calculate_pricing_methods()
        if data:
            return data["valor_orcamento"]
        return self.total_products_value + self.total_services_value

    @property
    def total_budget_value(self) -> Money:
        return self.total_base_value - self.discount_value

    @property
    def has_local_items(self):
        return self.items.filter(is_local=True).exists()

    @property
    def ordered_images(self):
        """Returns budget images ordered by upload date (oldest first)"""
        return self.budget_image.all()

    def __str__(self):
        return f"Budget #{self.id} - {self.customer}"


class BudgetImageType(models.TextChoices):
    PRINCIPAL = "principal", "Principal"
    FRONTAL = "frontal", "Frontal"
    TRASEIRA = "traseira", "Traseira"
    DIREITA = "direita", "Direita"
    ESQUERDA = "esquerda", "Esquerda"
    PAINEL = "painel", "Painel"
    CHASSI = "chassi", "Chassi"
    MOTOR = "motor", "Motor"
    ADDITIONAL = "additional", "Adicional"


class BudgetImage(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="budget_image")
    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name="budget_image")
    content = models.BinaryField(null=True, blank=True)
    content_name = models.CharField(max_length=100, null=True, blank=True)
    content_type = models.CharField(max_length=100, null=True, blank=True)
    image_type = models.CharField(max_length=20, choices=BudgetImageType.choices, default=BudgetImageType.ADDITIONAL, verbose_name="Tipo de Imagem")

    class Meta:
        verbose_name = "Imagem do Orçamento"
        verbose_name_plural = "Imagens do Orçamento"
        ordering = ["criado_em"]
        constraints = [models.UniqueConstraint(fields=["budget", "image_type"], condition=~models.Q(image_type=BudgetImageType.ADDITIONAL), name="unique_budget_image_type_non_additional")]

    def __str__(self):
        return f"Image #{self.id} from Budget: {self.budget}"


class BudgetItem(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="items")
    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name="items")

    # Referências
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    service = models.ForeignKey(Service, on_delete=models.SET_NULL, null=True, blank=True)
    kit = models.ForeignKey(Kit, on_delete=models.SET_NULL, null=True, blank=True)

    # Dados
    description = models.CharField(verbose_name="Descrição", max_length=100, default="")
    quantity = models.PositiveIntegerField(verbose_name="Quantidade", default=1)
    is_local = models.BooleanField(verbose_name="Item Local", default=False, help_text="Item criado apenas neste orçamento, não cadastrado no banco de dados")

    ## Produto
    shipping = MoneyField(verbose_name="Frete", max_digits=14, decimal_places=2, default=0)
    product_cost_price = MoneyField(verbose_name="Custo", max_digits=14, decimal_places=2, default=0)
    product_selling_price = MoneyField(verbose_name="Valor de Venda", max_digits=14, decimal_places=2, default=0)

    ## Serviço
    service_cost_price = MoneyField(verbose_name="Custo", max_digits=14, decimal_places=2, default=0)
    service_selling_price = MoneyField(verbose_name="Valor de Venda", max_digits=14, decimal_places=2, default=0)
    duration = models.DurationField(verbose_name="Duração", null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.pk:
            if self.product:
                self.product_cost_price = self.product.cost_price
                self.product_selling_price = self.product.selling_price
                self.description = self.product.name

            elif self.service:
                self.service_cost_price = self.service.suggested_cost or Money(0, "BRL")
                self.service_selling_price = self.service.selling_price
                self.duration = self.service.duration
                self.description = self.service.name

            elif self.kit:
                self.product_selling_price = sum((kp.product.selling_price * kp.quantity for kp in self.kit.kit_products.all()), Money(0, "BRL"))
                self.service_selling_price = sum((ks.service.selling_price * ks.quantity for ks in self.kit.kit_services.all()), Money(0, "BRL"))

                self.product_cost_price = sum((kp.product.cost_price * kp.quantity for kp in self.kit.kit_products.all()), Money(0, "BRL"))
                self.service_cost_price = sum((ks.service.suggested_cost * ks.quantity for ks in self.kit.kit_services.all() if ks.service.suggested_cost), Money(0, "BRL"))

                self.duration = sum((ks.service.duration for ks in self.kit.kit_services.all()), timedelta())
                self.description = self.kit.name

        super().save(*args, **kwargs)

    @property
    def duration_display(self):
        if not self.duration:
            return "00h 00m"

        total_seconds = int(self.duration.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60

        return f"{hours:02d}h {minutes:02d}m"

    def _get_kit_override_maps(self) -> tuple[dict[int, "BudgetKitItemOverride"], dict[int, "BudgetKitItemOverride"]]:
        product_overrides: dict[int, "BudgetKitItemOverride"] = {}
        service_overrides: dict[int, "BudgetKitItemOverride"] = {}

        for override in self.kit_overrides.select_related("product", "service"):
            if override.product_id:
                product_overrides[override.product_id] = override
            if override.service_id:
                service_overrides[override.service_id] = override

        return product_overrides, service_overrides

    @property
    def effective_kit_products(self) -> list[dict[str, Any]]:
        if not self.kit:
            return []

        product_overrides, _ = self._get_kit_override_maps()
        products: list[dict[str, Any]] = []

        for kit_product in self.kit.kit_products.select_related("product").all():
            override = product_overrides.get(kit_product.product_id)
            quantity = override.quantity if override else kit_product.quantity
            if quantity <= 0:
                continue

            products.append({"id": kit_product.product_id, "name": kit_product.product.name, "quantity": quantity})

        return products

    @property
    def effective_kit_services(self) -> list[dict[str, Any]]:
        if not self.kit:
            return []

        _, service_overrides = self._get_kit_override_maps()
        services: list[dict[str, Any]] = []

        for kit_service in self.kit.kit_services.select_related("service").all():
            override = service_overrides.get(kit_service.service_id)
            quantity = override.quantity if override else kit_service.quantity
            if quantity <= 0:
                continue

            services.append({"id": kit_service.service_id, "name": kit_service.service.name, "quantity": quantity})

        return services

    @property
    def effective_kit_products_count(self) -> int:
        return len(self.effective_kit_products)

    @property
    def effective_kit_services_count(self) -> int:
        return len(self.effective_kit_services)

    @property
    def total_price(self):
        # Se for kit, calcular com base nos overrides
        if self.kit:
            return self.get_kit_total_with_overrides()
        return ((self.product_selling_price + self.service_selling_price) * self.quantity) + self.shipping

    def get_kit_total_with_overrides(self):
        """Calcula o total do kit considerando os overrides

        Total = (Soma total de produtos) + (Soma total de serviços)
        Produto total = (preço * quantidade do produto) + frete
        Serviço total = preço * quantidade do serviço

        Depois multiplica pela quantidade de kits no orçamento
        """
        if not self.kit:
            return Money(0, "BRL")

        total_produtos = Money(0, "BRL")
        total_servicos = Money(0, "BRL")

        # Calcular total dos produtos: (preço * qtd) + frete para cada produto
        for kit_product in self.kit.kit_products.select_related("product").all():
            override = self.kit_overrides.filter(product=kit_product.product).first()
            if override:
                if override.quantity <= 0:
                    produto_subtotal = Money(0, "BRL")
                else:
                    produto_subtotal = (override.product_selling_price * override.quantity) + override.shipping
            elif kit_product.quantity > 0:
                produto_subtotal = (kit_product.product.selling_price * kit_product.quantity) + Money(0, "BRL")
            else:
                produto_subtotal = Money(0, "BRL")
            total_produtos += produto_subtotal

        # Calcular total dos serviços: preço * qtd para cada serviço
        for kit_service in self.kit.kit_services.select_related("service").all():
            override = self.kit_overrides.filter(service=kit_service.service).first()
            if override:
                if override.quantity <= 0:
                    servico_subtotal = Money(0, "BRL")
                else:
                    servico_subtotal = override.service_selling_price * override.quantity
            elif kit_service.quantity > 0:
                servico_subtotal = kit_service.service.selling_price * kit_service.quantity
            else:
                servico_subtotal = Money(0, "BRL")
            total_servicos += servico_subtotal

        # Total do kit = soma de produtos + soma de serviços
        total_kit = total_produtos + total_servicos

        # Multiplicar pela quantidade de kits no orçamento
        return total_kit * self.quantity

    def get_kit_products_total(self):
        """Retorna apenas o total de produtos do kit (para resumo separado)"""
        if not self.kit:
            return Money(0, "BRL")

        total_produtos = Money(0, "BRL")
        for kit_product in self.kit.kit_products.select_related("product").all():
            override = self.kit_overrides.filter(product=kit_product.product).first()
            if override:
                if override.quantity <= 0:
                    produto_subtotal = Money(0, "BRL")
                else:
                    produto_subtotal = (override.product_selling_price * override.quantity) + override.shipping
            elif kit_product.quantity > 0:
                produto_subtotal = (kit_product.product.selling_price * kit_product.quantity) + Money(0, "BRL")
            else:
                produto_subtotal = Money(0, "BRL")
            total_produtos += produto_subtotal

        return total_produtos * self.quantity

    def get_kit_services_total(self):
        """Retorna apenas o total de serviços do kit (para resumo separado)"""
        if not self.kit:
            return Money(0, "BRL")

        total_servicos = Money(0, "BRL")
        for kit_service in self.kit.kit_services.select_related("service").all():
            override = self.kit_overrides.filter(service=kit_service.service).first()
            if override:
                if override.quantity <= 0:
                    servico_subtotal = Money(0, "BRL")
                else:
                    servico_subtotal = override.service_selling_price * override.quantity
            elif kit_service.quantity > 0:
                servico_subtotal = kit_service.service.selling_price * kit_service.quantity
            else:
                servico_subtotal = Money(0, "BRL")
            total_servicos += servico_subtotal

        return total_servicos * self.quantity

    def get_kit_services_duration(self):
        """Retorna a duração total dos serviços do kit"""
        if not self.kit:
            return timedelta(0)

        total_duration = timedelta(0)
        for kit_service in self.kit.kit_services.select_related("service").all():
            override = self.kit_overrides.filter(service=kit_service.service).first()
            if override:
                if override.quantity > 0 and override.duration:
                    total_duration += override.duration * override.quantity
            elif kit_service.quantity > 0 and kit_service.service.duration:
                total_duration += kit_service.service.duration * kit_service.quantity

        return total_duration * self.quantity

    def get_kit_products_shipping_total(self):
        if not self.kit:
            return Money(0, "BRL")

        total_shipping = Money(0, "BRL")
        for kit_product in self.kit.kit_products.select_related("product").all():
            override = self.kit_overrides.filter(product=kit_product.product).first()
            if override and override.quantity > 0:
                total_shipping += override.shipping

        return total_shipping * self.quantity

    def get_kit_products_cost_total(self):
        if not self.kit:
            return Money(0, "BRL")

        total_cost = Money(0, "BRL")
        for kit_product in self.kit.kit_products.select_related("product").all():
            override = self.kit_overrides.filter(product=kit_product.product).first()
            if override:
                if override.quantity <= 0:
                    continue
                total_cost += override.product_cost_price * override.quantity
            elif kit_product.quantity > 0:
                total_cost += kit_product.product.cost_price * kit_product.quantity

        return total_cost * self.quantity

    def get_kit_services_cost_total(self):
        if not self.kit:
            return Money(0, "BRL")

        total_cost = Money(0, "BRL")
        for kit_service in self.kit.kit_services.select_related("service").all():
            override = self.kit_overrides.filter(service=kit_service.service).first()
            if override:
                if override.quantity <= 0:
                    continue
                total_cost += override.service_cost_price * override.quantity
            elif kit_service.quantity > 0 and kit_service.service.suggested_cost:
                total_cost += kit_service.service.suggested_cost * kit_service.quantity

        return total_cost * self.quantity

    def get_kit_third_party_services_cost_total(self):
        if not self.kit:
            return Money(0, "BRL")

        total_cost = Money(0, "BRL")
        for kit_service in self.kit.kit_services.select_related("service").all():
            if not kit_service.service.is_third_party:
                continue

            override = self.kit_overrides.filter(service=kit_service.service).first()
            if override:
                if override.quantity <= 0:
                    continue
                total_cost += override.service_cost_price * override.quantity
            elif kit_service.quantity > 0 and kit_service.service.suggested_cost:
                total_cost += kit_service.service.suggested_cost * kit_service.quantity

        return total_cost * self.quantity

    def get_kit_third_party_services_selling_total(self):
        if not self.kit:
            return Money(0, "BRL")

        total_selling = Money(0, "BRL")
        for kit_service in self.kit.kit_services.select_related("service").all():
            if not kit_service.service.is_third_party:
                continue

            override = self.kit_overrides.filter(service=kit_service.service).first()
            if override:
                if override.quantity <= 0:
                    continue
                total_selling += override.service_selling_price * override.quantity
            elif kit_service.quantity > 0:
                total_selling += kit_service.service.selling_price * kit_service.quantity

        return total_selling * self.quantity

    @property
    def unit_price(self):
        if self.quantity == 0:
            return Money(0, "BRL")
        return Money((self.product_selling_price + self.service_selling_price).amount / self.quantity, "BRL")

    @property
    def profit_value(self):
        return Money((self.product_selling_price.amount + self.service_selling_price.amount) - (self.product_cost_price.amount + self.service_cost_price.amount), "BRL")

    class Meta:
        verbose_name = "Item do Orçamento"
        verbose_name_plural = "Itens do Orçamento"


class BudgetKitItemOverride(TimeStampedModel):
    """Armazena modificações de itens do kit específicas para este orçamento"""

    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="kit_overrides")
    budget_item = models.ForeignKey(BudgetItem, on_delete=models.CASCADE, related_name="kit_overrides")

    # Referência ao item original do kit (um dos dois deve estar preenchido)
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.CASCADE)
    service = models.ForeignKey(Service, null=True, blank=True, on_delete=models.CASCADE)

    # Campos editáveis
    quantity = models.IntegerField(verbose_name="Quantidade", default=1, validators=[MinValueValidator(0)])

    # Campos de Produto
    product_cost_price = MoneyField(verbose_name="Custo do Produto", max_digits=14, decimal_places=2, default=0, default_currency="BRL")
    product_selling_price = MoneyField(verbose_name="Preço de Venda do Produto", max_digits=14, decimal_places=2, default=0, default_currency="BRL")
    shipping = MoneyField(verbose_name="Frete", max_digits=14, decimal_places=2, default=0, default_currency="BRL")

    # Campos de Serviço
    service_cost_price = MoneyField(verbose_name="Custo do Serviço", max_digits=14, decimal_places=2, default=0, default_currency="BRL")
    service_selling_price = MoneyField(verbose_name="Preço de Venda do Serviço", max_digits=14, decimal_places=2, default=0, default_currency="BRL")
    duration = models.DurationField(verbose_name="Duração", null=True, blank=True)

    class Meta:
        verbose_name = "Override de Item do Kit"
        verbose_name_plural = "Overrides de Itens do Kit"
        # Garantir que não haja duplicatas
        constraints = [
            models.UniqueConstraint(fields=["budget_item", "product"], condition=models.Q(product__isnull=False), name="unique_budget_kit_product"),
            models.UniqueConstraint(fields=["budget_item", "service"], condition=models.Q(service__isnull=False), name="unique_budget_kit_service"),
        ]

    def __str__(self):
        if self.product:
            return f"Override: {self.product.name} - Budget #{self.budget_item.budget_id}"
        elif self.service:
            return f"Override: {self.service.name} - Budget #{self.budget_item.budget_id}"
        return f"Override #{self.id}"
