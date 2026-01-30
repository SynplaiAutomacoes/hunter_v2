from django.core.exceptions import ValidationError

def is_valid_cpf(cpf: str) -> bool:
    cpf = ''.join(c for c in cpf if c.isdigit())

    if len(cpf) != 11:
        return False

    if cpf == cpf[0] * 11:
        return False

    total = sum(int(cpf[i]) * (10 - i) for i in range(9))
    first_digit = (total * 10 % 11) % 10

    total = sum(int(cpf[i]) * (11 - i) for i in range(10))
    second_digit = (total * 10 % 11) % 10

    return cpf[-2:] == f"{first_digit}{second_digit}"


def is_valid_cnpj(cnpj: str) -> bool:
    cnpj = ''.join(c for c in cnpj if c.isdigit())

    if len(cnpj) != 14:
        return False

    if cnpj == cnpj[0] * 14:
        return False

    weights_first = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    weights_second = [6] + weights_first

    def calculate_digit(partial, weights):
        total = sum(int(d) * w for d, w in zip(partial, weights))
        remainder = total % 11
        return '0' if remainder < 2 else str(11 - remainder)

    first_digit = calculate_digit(cnpj[:12], weights_first)
    second_digit = calculate_digit(cnpj[:12] + first_digit, weights_second)

    return cnpj[-2:] == first_digit + second_digit


def is_valid_cpf_or_cnpj(value: str) -> bool:
    value = ''.join(c for c in value if c.isdigit())

    if len(value) == 11:
        return is_valid_cpf(value)
    if len(value) == 14:
        return is_valid_cnpj(value)
    return False


def cpf_or_cnpj_validator(value: str):
    if not is_valid_cpf_or_cnpj(value):
        raise ValidationError("Informe um CPF ou CNPJ válido.")