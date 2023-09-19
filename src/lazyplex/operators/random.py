import random as _random
from collections.abc import Iterable
from numbers import Number
from typing import Any

from ..core import as_lazy

__all__ = [
    "random",
    "uniform",
    "triangular",
    "randint",
    "randrange",
    "sample",
    "choices",
    "normalvariate",
    "lognormvariate",
    "expovariate",
    "vonmisesvariate",
    "gammavariate",
    "gauss",
    "betavariate",
    "paretovariate",
    "weibullvariate",
    "getstate",
    "setstate",
    "getrandbits",
    "randbytes",
]

for item in dir(_random):
    if item in __all__:
       globals()[item] = as_lazy(getattr(_random, item))


@as_lazy
def randnum(min: Number, max: Number, decimals: Number = 0):
    return round(min + (max - min) * _random.random(), decimals)


@as_lazy
def choice(*values: Any):
    if len(values) == 1 and isinstance(values[0], Iterable):
        values = values[0]
    return _random.choice(values)


@as_lazy
def shuffle(*values: Any):
    if len(values) == 1 and isinstance(values[0], Iterable):
        values = values[0]
    return _random.shuffle(values)