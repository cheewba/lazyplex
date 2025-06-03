import asyncio
import types
import warnings
from functools import wraps
from inspect import isawaitable


def as_future(value):
    if isawaitable(value):
        return asyncio.ensure_future(value)

    fut = asyncio.Future()
    fut.set_result(value)
    return fut


def dummy(*args, **kwargs): pass


def isasyncgen(item):
    return isinstance(item, types.AsyncGeneratorType)


def deprecated(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        warnings.warn(
            f"{func.__name__} is deprecated and will be removed in future versions.",
            DeprecationWarning,
            stacklevel=2
        )
        return func(*args, **kwargs)
    return wrapper