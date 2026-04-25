from django import forms
from apps.core.widgets import SearchableSelectInput, TextInput, TextareaInput, CalendarDateInput, MoneyInput
from apps.finance.models import MovementGroup, FinancialMovement


class GroupMovementStep1Form(forms.Form):
    entity = forms.ChoiceField(
        label="Fornecedor ou Colaborador",
        widget=SearchableSelectInput(),
        required=True
    )

    def __init__(self, *args, **kwargs):
        suppliers = kwargs.pop('suppliers', [])
        collaborators = kwargs.pop('collaborators', [])
        super().__init__(*args, **kwargs)

        choices = [('', '---------')]
        
        for s in suppliers:
            choices.append((f'supplier_{s.id}', f'Fornecedor: {s.name}'))
        
        for c in collaborators:
            choices.append((f'collaborator_{c.id}', f'Colaborador: {str(c)}'))
            
        self.fields['entity'].choices = choices


class GroupMovementStep3Form(forms.ModelForm):
    class Meta:
        model = MovementGroup
        fields = ['name', 'description', 'due_date']
        widgets = {
            'name': TextInput(),
            'description': TextareaInput(attrs={'rows': 3}),
            'due_date': CalendarDateInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['name'].required = True
        self.fields['due_date'].required = True
