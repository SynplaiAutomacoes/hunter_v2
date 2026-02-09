from django.urls import reverse
from crispy_forms.layout import Div, Field, HTML
from apps.core.widgets import CEPInput, TextInput, SelectInput
from django.db import transaction
from apps.budget.models import BudgetStatus


class AddressFormMixin:
    """Mixin para centralizar widgets e lógica de readonly do endereço."""

    def setup_address_fields(self):
        # Configura os widgets de endereço
        address_widgets = {
            "cep": CEPInput(),
            "logradouro": TextInput(),
            "numero": TextInput(),
            "complemento": TextInput(),
            "bairro": TextInput(),
            "cidade": TextInput(),
            "estado": SelectInput(),
        }

        for field_name, widget in address_widgets.items():
            if field_name in self.fields:
                self.fields[field_name].widget = widget
                if field_name == "estado":
                    self.fields[field_name].widget = SelectInput(
                        choices=self.fields[field_name].choices,
                        attrs={"class": "form-control"},
                    )

        # Bloqueio dos campos antes do usuário preencher o campo CEP
        for field in ["logradouro", "bairro", "cidade"]:
            if field in self.fields:
                self.fields[field].widget.attrs.update({"readonly": True, "style": "cursor: not-allowed;", "title": "Preencha o campo de CEP"})


def address_layout() -> Div:
    return Div(
        HTML("""
            <div class="col-span-12" style="display: flex; align-items: center; gap: 25px;">
                <h3 class="text-xl font-bold">Endereço</h3>
                <h5 id="cep-loader" class="htmx-indicator" style="margin:0;">
                    <span class="text-lg font-semibold">(Buscando endereço...)</span>
                </h5>
            </div>
        """),
        Field("cep", wrapper_class="col-span-12 lg:col-span-4", hx_get=reverse("core:cep_lookup"), hx_trigger="blur", hx_target="this", hx_swap="none", hx_include="[name='cep']", hx_indicator="#cep-loader"),
        Field("logradouro", wrapper_class="col-span-12 lg:col-span-4"),
        Field("numero", wrapper_class="col-span-12 lg:col-span-4"),
        #
        Field("complemento", wrapper_class="col-span-12 lg:col-span-4"),
        Field("bairro", wrapper_class="col-span-12 lg:col-span-4"),
        Field("cidade", wrapper_class="col-span-12 lg:col-span-4"),
        #
        Field("estado", wrapper_class="col-span-12 lg:col-span-4"),
        css_class="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start col-span-12",
    )


class MultiStepFormMixin:
    steps_definition = []

    @property
    def budget_object(self):
        if not hasattr(self, "get_object"):
            return None
        if not hasattr(self, "_budget_obj"):
            self._budget_obj = self.get_object()
        return self._budget_obj

    def get_steps_config(self):
        if hasattr(self, "get_steps_definition"):
            return self.get_steps_definition()
        return self.steps_definition

    def get_current_step(self):
        step_url = self.request.GET.get("step")
        try:
            step = int(step_url) if step_url else None
        except (ValueError, TypeError):
            step = None

        if not step:
            obj = self.budget_object
            if obj and hasattr(obj, "current_step"):
                step = obj.current_step
            else:
                step = 1

        total_steps = len(self.get_steps_config())
        if step > total_steps:
            return total_steps
        return max(1, step)

    def get_form_class(self):
        """Retorna o form_class definido para a etapa atual."""
        current_step = self.get_current_step()
        steps = self.get_steps_config()

        if not steps:
            return None

        idx = max(0, min(current_step - 1, len(steps) - 1))
        return steps[idx].get("form_class")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        obj = self.get_object() if hasattr(self, "get_object") else None

        if obj:
            kwargs["instance"] = obj
        elif "instance" in kwargs:
            kwargs.pop("instance")

        if hasattr(self, "workshop"):
            kwargs.update({'workshop': self.workshop})
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        current_step = self.get_current_step()
        steps = self.get_steps_config()

        context["steps_config"] = [{"number": i + 1, "title": step["title"]} for i, step in enumerate(steps)]
        context["current_step"] = current_step

        context["object"] = self.budget_object
        context["max_reached_step"] = self.budget_object.current_step if self.budget_object else 1

        if steps and current_step <= len(steps):
            step_config = steps[current_step - 1]
            if "formset_class" in step_config:
                obj = getattr(self, 'object', self.budget_object)
                context["step_formset"] = step_config["formset_class"](
                    instance=obj,
                    data=self.request.POST if self.request.method == "POST" else None
                )
        return context

    def apply_step_status(self, budget=None, current_step=None, actor=None, isUpdate=False):
        """
        Aplica automaticamente o status configurado para a etapa atual, se houver.

        Regras:
        - Usa `self.steps_definition[current_step - 1]` para ler `status` e `auto_apply`.
        - Não aplica se `auto_apply` for False ou se `status` não estiver definido.
        - Não rebaixa status terminal (ex.: approved, rejected, cancelled).
        - Valida que o status alvo pertence a `BudgetStatus`.
        - Faz a alteração de forma atômica e salva apenas o campo de status.
        - Em update, não altera a badge caso seja anterior a etapa 4

        Retorna True se uma alteração foi aplicada, False caso contrário.
        """
        steps = self.get_steps_config()

        if budget is None:
            budget = getattr(self, 'object', None) or getattr(self, 'budget_object', None)
        if budget is None:
            return False

        if current_step is None:
            current_step = self.get_current_step()

        # Defensive: ensure step index in range
        if not (1 <= current_step <= len(steps)):
            return False

        step_config = steps[current_step - 1]
        auto_apply = step_config.get('auto_apply', False)
        desired = step_config.get('status', None)

        if not auto_apply or not desired:
            return False

        if isUpdate and current_step < 4:
            # Em updates, não rebaixa a badge caso seja anterior a etapa 4
            return False

        # Normalize desired status to a string value
        try:
            # If provided as TextChoices member, .value exists
            new_status = desired.value if hasattr(desired, 'value') else str(desired)
        except Exception:
            new_status = str(desired)

        # Validate status
        try:
            BudgetStatus(new_status)
        except Exception:
            # invalid status specified in steps_definition; ignore
            return False

        # Do not override terminal statuses
        terminal = {BudgetStatus.APPROVED, BudgetStatus.REJECTED, BudgetStatus.CANCELLED}
        if budget.status in terminal:
            return False

        # If already the same status, nothing to do
        if budget.status == new_status:
            return False

        # Apply change atomically
        actor = actor or getattr(self, 'request', None) and getattr(self.request, 'user', None)
        with transaction.atomic():
            # reload instance with select_for_update if possible to avoid races
            try:
                locked = budget.__class__.objects.select_for_update().get(pk=budget.pk)
            except Exception:
                locked = budget

            locked.status = new_status
            # Persist only status
            locked.save(update_fields=['status'])

        return True
