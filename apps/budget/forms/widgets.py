from django import forms


class MultipleFileInput(forms.FileInput):
    """Custom widget to support multiple file uploads with preview"""

    allow_multiple_selected = True
    template_name = "widgets/multiple_image_input.html"

    def __init__(self, attrs=None):
        if attrs is None:
            attrs = {}
        attrs["multiple"] = True
        super().__init__(attrs)

    def value_from_datadict(self, data, files, name):
        if hasattr(files, "getlist"):
            return files.getlist(name)
        return files.get(name)
