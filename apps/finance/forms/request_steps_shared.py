from __future__ import annotations

from html import escape

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout

from apps.core.presentation.widgets import SearchableSelectInput
from apps.workorder.models import WorkOrder, WorkOrderStatus
from apps.core.presentation.forms import CoreModelForm


class SharedEmissionWorkorderSelectionForm(CoreModelForm):
    step_title = "Selecionar Ordem de Servico"
    step_subtitle = "Selecione a ordem de servico aprovada que sera utilizada para emitir a nota fiscal."
    workorder_label = "Ordem de Servico"
    empty_customer_label = "Cliente nao informado"

    def __init__(self, *args, **kwargs):
        workshop = kwargs.pop("workshop", None)
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        queryset = WorkOrder.objects.none()
        if workshop is not None:
            queryset = WorkOrder.objects.filter(workshop=workshop, status=WorkOrderStatus.APPROVED).select_related(
                "budget",
                "budget__customer",
                "budget__vehicle",
            )

        field = self.fields["workorder"]
        field.queryset = queryset.order_by("-id")

        def _label_from_instance(workorder: WorkOrder) -> str:
            customer = getattr(getattr(workorder, "budget", None), "customer", None)
            customer_name = customer.name if customer else self.empty_customer_label
            return f"Ordem de Servico - {customer_name} - #{workorder.pk}"

        field.label_from_instance = _label_from_instance
        field.widget = SearchableSelectInput(choices=field.choices)
        field.label = self.workorder_label

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                HTML(f"<h2 class='text-2xl font-bold'>{self.step_title}</h2>"),
                HTML(f"<p class='text-base-content/70 mb-6'>{self.step_subtitle}</p>"),
                Field("workorder"),
                css_class="space-y-4",
            )
        )


class SharedEmissionCustomerReviewForm(CoreModelForm):
    step_title = "Conferir dados do cliente"
    step_subtitle = "Valide os dados do cliente antes de avancar para a etapa de emissao."
    empty_value_label = "Nao informado"
    address_label = "Endereco"
    vehicle_label = "Veiculo"

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        customer = None
        vehicle = None
        if self.instance and self.instance.workorder_id:
            budget = self.instance.workorder.budget
            customer = budget.customer
            vehicle = budget.vehicle

        empty_value = self.empty_value_label
        customer_name = escape(customer.name) if customer else empty_value
        customer_doc = escape(customer.cpf_or_cnpj_formatted) if customer else empty_value
        customer_phone = escape(str(customer.phone)) if customer and customer.phone else empty_value
        customer_email = escape(customer.email) if customer and customer.email else empty_value
        customer_address = escape(customer.full_address) if customer else empty_value
        vehicle_value = escape(str(vehicle)) if vehicle else empty_value

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                HTML(f"<h2 class='text-2xl font-bold'>{self.step_title}</h2>"),
                HTML(f"<p class='text-base-content/70 mb-6'>{self.step_subtitle}</p>"),
                HTML(
                    f"""
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 bg-base-200 p-5 rounded-xl">
                        <div>
                            <p class="text-xs uppercase text-base-content/60">Cliente</p>
                            <p class="font-semibold">{customer_name}</p>
                        </div>
                        <div>
                            <p class="text-xs uppercase text-base-content/60">Documento</p>
                            <p class="font-semibold">{customer_doc}</p>
                        </div>
                        <div>
                            <p class="text-xs uppercase text-base-content/60">Telefone</p>
                            <p class="font-semibold">{customer_phone}</p>
                        </div>
                        <div>
                            <p class="text-xs uppercase text-base-content/60">E-mail</p>
                            <p class="font-semibold">{customer_email}</p>
                        </div>
                        <div class="md:col-span-2">
                            <p class="text-xs uppercase text-base-content/60">{self.address_label}</p>
                            <p class="font-semibold">{customer_address}</p>
                        </div>
                        <div class="md:col-span-2">
                            <p class="text-xs uppercase text-base-content/60">{self.vehicle_label}</p>
                            <p class="font-semibold">{vehicle_value}</p>
                        </div>
                    </div>
                    """
                ),
                css_class="space-y-4",
            )
        )
