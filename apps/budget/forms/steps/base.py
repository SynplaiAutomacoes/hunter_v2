from apps.core.presentation.forms import CoreModelForm


class BudgetStepBaseForm(CoreModelForm):
    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.request = kwargs.pop("request", None)
        kwargs.pop("receipt_terms", None)
        kwargs.pop("term_signings_by_template_id", None)
        super().__init__(*args, **kwargs)
