from numbers import Number

from ..core.actions import as_lazy


@as_lazy
def format(text, *args, **kwargs):
    return text.format(*args, **kwargs)


def seconds(value: Number) -> Number:
    return value


def minutes(value: Number) -> Number:
    return seconds(value * 60)


def hours(value: Number) -> Number:
    return minutes(value * 60)


def days(value: Number) -> Number:
    return hours(value * 24)