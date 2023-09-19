import asyncio
import types
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