from apps.core.presentation.forms import CoreModelForm


class BudgetStepBaseForm(CoreModelForm):
    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)
