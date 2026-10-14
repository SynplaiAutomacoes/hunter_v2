from __future__ import annotations

from django import forms

from apps.budget.models import BudgetStatus
from apps.yard.models import YardColumn, YardColumnTarget, STATUS_ALL
from apps.workorder.models import WorkOrderStatus


def yard_status_choices() -> list[tuple[str, list[tuple[str, str]]]]:
    return [
        ("Geral", [(STATUS_ALL, "Todos")]),
        ("Orçamentos", list(BudgetStatus.choices)),
        ("Ordens de Serviço", list(WorkOrderStatus.choices)),
    ]


def yard_status_choices_for_target(target: str) -> list[tuple[str, str]]:
    if target == YardColumnTarget.BUDGET:
        return [(STATUS_ALL, "Todos"), *list(BudgetStatus.choices)]
    if target == YardColumnTarget.WORKORDER:
        return [(STATUS_ALL, "Todos"), *list(WorkOrderStatus.choices)]
    return [(STATUS_ALL, "Todos")]


class YardColumnForm(forms.ModelForm):
    class Meta:
        model = YardColumn
        fields = ["target", "status", "title", "color", "date_base", "is_active"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "input input-bordered w-full", "placeholder": "Ex.: Aguardando Peças"}),
            "color": forms.TextInput(attrs={"type": "color", "class": "input input-bordered w-24 h-10 p-1"}),
            "target": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "status": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "date_base": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "is_active": forms.CheckboxInput(attrs={"class": "checkbox checkbox-primary"}),
        }
        labels = {
            "target": "Modelo",
            "status": "Status",
            "title": "Título de exibição",
            "color": "Cor da coluna",
            "date_base": "Base de data",
            "is_active": "Coluna ativa",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["status"].choices = yard_status_choices()

    def clean(self) -> dict:
        cleaned_data = super().clean()
        target = cleaned_data.get("target")
        status = cleaned_data.get("status")
        if target and status:
            valid = {value for value, _label in yard_status_choices_for_target(target)}
            if status not in valid:
                self.add_error("status", "Status inválido para o modelo selecionado.")
                return cleaned_data
            workshop_id = getattr(getattr(self, "instance", None), "workshop_id", None)
            if workshop_id:
                exists = (
                    YardColumn.objects.filter(workshop_id=workshop_id, target=target, status=status)
                    .exclude(pk=getattr(self.instance, "pk", None))
                    .exists()
                )
                if exists:
                    self.add_error("status", "Já existe uma coluna para este modelo e status.")
        return cleaned_data
