from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model
from apps.core.presentation.widgets import SearchableSelectInput
from apps.workshops.models.workshops import Workshop

User = get_user_model()


class NotificationBroadcastForm(forms.Form):
    workshop_select = forms.ChoiceField(
        required=False,
        label="Adicionar Oficina Alvo",
        widget=SearchableSelectInput(choices=[]),
        help_text="Pesquise e selecione oficinas para adicionar à lista de destinatários.",
    )
    user_select = forms.ChoiceField(
        required=False,
        label="Adicionar Usuário Específico",
        widget=SearchableSelectInput(choices=[]),
        help_text="Pesquise e selecione usuários para adicionar à lista de destinatários.",
    )
    workshops = forms.ModelMultipleChoiceField(
        queryset=Workshop.objects.filter(is_active=True).order_by("name"),
        required=False,
        widget=forms.MultipleHiddenInput(),
    )
    users = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(is_active=True).order_by("username"),
        required=False,
        widget=forms.MultipleHiddenInput(),
    )
    title = forms.CharField(
        max_length=255,
        label="Título da Notificação",
        widget=forms.TextInput(attrs={"class": "input input-bordered w-full", "placeholder": "Digite o título da mensagem..."}),
    )
    message = forms.CharField(
        max_length=2000,
        label="Conteúdo da Notificação",
        widget=forms.Textarea(attrs={"class": "textarea textarea-bordered w-full", "rows": 5, "placeholder": "Digite a mensagem que será enviada aos destinatários..."}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        workshop_choices = [("", "Pesquisar oficina...")] + [
            (str(w.id), w.name) for w in Workshop.objects.filter(is_active=True).order_by("name")
        ]
        self.fields["workshop_select"].choices = workshop_choices
        self.fields["workshop_select"].widget.choices = workshop_choices

        user_choices = [("", "Pesquisar usuário...")] + [
            (str(u.id), f"{u.get_full_name()} ({u.username})" if u.get_full_name() else u.username)
            for u in User.objects.filter(is_active=True).order_by("username")
        ]
        self.fields["user_select"].choices = user_choices
        self.fields["user_select"].widget.choices = user_choices

    def clean(self):
        cleaned_data = super().clean()
        workshops = cleaned_data.get("workshops")
        users = cleaned_data.get("users")

        if not workshops and not users:
            raise forms.ValidationError("Selecione pelo menos uma oficina ou um usuário destinatário para enviar a notificação.")

        return cleaned_data
