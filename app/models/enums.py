from enum import StrEnum


def enum_values[E: StrEnum](enum_cls: type[E]) -> list[str]:
    return [member.value for member in enum_cls]
