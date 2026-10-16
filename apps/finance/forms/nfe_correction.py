from __future__ import annotations

from django import forms

from apps.core.presentation.forms import CoreForm
from apps.finance.services.nfe_events import CCE_MAX_SEQUENCE, CCE_MAX_TEXT_LENGTH, CCE_MIN_TEXT_LENGTH, NfeCorrectionError, parse_nfe_correction_identifier


CCE_EVENT_SEQUENCE_CHOICES: tuple[tuple[str, str], ...] = tuple((str(value), str(value)) for value in range(1, CCE_MAX_SEQUENCE + 1))


class NfeExternalCorrectionForm(CoreForm):
    access_key_or_uuid = forms.CharField(
        label="Chave de acesso ou UUID da Nota Fiscal",
        max_length=80,
        widget=forms.TextInput(
            attrs={
                "class": "input input-bordered w-full font-mono",
                "placeholder": "3123 0748 3410 2700 0174 5500 1000 0001 2345 6789 0123",
                "autocomplete": "off",
            }
        ),
    )
    event_sequence = forms.ChoiceField(
        label="Nº do Evento",
        choices=CCE_EVENT_SEQUENCE_CHOICES,
        initial="1",
        widget=forms.Select(attrs={"class": "select select-bordered w-full"}),
    )
    correction = forms.CharField(
        label="Correção",
        min_length=CCE_MIN_TEXT_LENGTH,
        max_length=CCE_MAX_TEXT_LENGTH,
        widget=forms.Textarea(
            attrs={
                "class": "textarea textarea-bordered w-full",
                "rows": 6,
                "placeholder": "Descreva a correção textual permitida pela CC-e.",
            }
        ),
    )
    confirm_legal_restrictions = forms.BooleanField(
        label="Confirmo que a correção respeita as restrições legais da CC-e.",
        required=True,
        widget=forms.CheckboxInput(attrs={"class": "checkbox checkbox-sm"}),
    )

    def clean_access_key_or_uuid(self) -> str:
        raw_value = str(self.cleaned_data.get("access_key_or_uuid") or "")
        try:
            _kind, normalized = parse_nfe_correction_identifier(raw_value)
        except NfeCorrectionError as exc:
            raise forms.ValidationError(str(exc)) from exc
        return normalized

    def clean_event_sequence(self) -> int:
        raw_value = self.cleaned_data.get("event_sequence")
        try:
            sequence = int(str(raw_value or "").strip())
        except (TypeError, ValueError) as exc:
            raise forms.ValidationError("Informe um número de evento entre 1 e 20.") from exc
        if sequence < 1 or sequence > CCE_MAX_SEQUENCE:
            raise forms.ValidationError("Informe um número de evento entre 1 e 20.")
        return sequence

    def clean_correction(self) -> str:
        return str(self.cleaned_data.get("correction") or "").strip()
