from django import template

from apps.core.text_normalization import name_case, plate_case, sentence_case

register = template.Library()


@register.filter(name="sentence_case")
def sentence_case_filter(value: object) -> str:
    if value is None:
        return ""
    return sentence_case(str(value))


@register.filter(name="name_case")
def name_case_filter(value: object) -> str:
    if value is None:
        return ""
    return name_case(str(value))


@register.filter(name="plate_case")
def plate_case_filter(value: object) -> str:
    if value is None:
        return ""
    return plate_case(str(value))
