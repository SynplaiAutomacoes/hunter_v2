from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model
from apps.workshops.models.workshops import Workshop

User = get_user_model()


class NotificationBroadcastForm(forms.Form):
    workshops = forms.ModelMultipleChoiceField(
        queryset=Workshop.objects.filter(is_active=True).order_by("name"),
        required=False,
        label="Oficinas Alvo",
        widget=forms.SelectMultiple(attrs={"class": "select select-bordered w-full h-32"}),
        help_text="Selecione uma ou mais oficinas. Deixe em branco se quiser selecionar usuários diretamente.",
    )
    users = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(is_active=True).order_by("username"),
        required=False,
        label="Usuários Específicos",
        widget=forms.SelectMultiple(attrs={"class": "select select-bordered w-full h-32"}),
        help_text="Selecione usuários específicos. Se oficinas forem selecionadas, filtrará pelos membros ativos das oficinas.",
    )
    title = forms.CharField(
        max_length=255,
        label="Título",
        widget=forms.TextInput(attrs={"class": "input input-bordered w-full", "placeholder": "Digite o título..."}),
    )
    message = forms.CharField(
        label="Mensagem",
        widget=forms.Textarea(attrs={"class": "textarea textarea-bordered w-full", "rows": 4, "placeholder": "Digite a mensagem..."}),
    )

    def clean(self):
        cleaned_data = super().clean()
        workshops = cleaned_data.get("workshops")
        users = cleaned_data.get("users")

        if not workshops and not users:
            raise forms.ValidationError("Selecione pelo menos uma oficina ou um usuário destinatário.")

        return cleaned_data
