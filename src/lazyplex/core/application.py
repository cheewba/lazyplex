import asyncio
import logging
from functools import partial
from inspect import signature, Signature, isgenerator
from typing import Any, Iterable, Iterator

from .constants import CTX_APPLICATION
from .context import branch, get_context
from .actions import Action, Lazy
from .helpers import as_future, dummy, isasyncgen
from .plugin import Plugins

logger = logging.getLogger(__name__)


class Application:
    name: str
    plugins: Plugins

    __get_action: None
    __get_action_sig: Signature
    __initializer = None

    @property
    def context_key(self):
        name = 'item'
        if self.__get_action_sig:
            args = list(self.__get_action_sig.parameters.keys())
            if args:
                name = args[0]
        return name

    def __init__(self, initializer, name=None) -> None:
        self.name = name or initializer.__name__
        self.plugins = Plugins()
        self.__initializer = staticmethod(initializer)

    def run_until_complete(self):
        asyncio.get_event_loop().run_until_complete(self())

    def __call__(self):
        async def wrapper():
            ctx = get_context()
            ctx.update(await self.get_application_context())

            app_init = self.__initializer()
            if isasyncgen(app_init):
                iterable = await anext(app_init)
                _send, _throw = app_init.asend, app_init.athrow
            elif isgenerator(app_init):
                iterable = next(app_init)
                _send, _throw = app_init.send, app_init.throw
            else:
                iterable = await as_future(app_init)
                _send, _throw = dummy, dummy

            try:
                result = await self.process_all(iterable)

                await as_future(_send(result))
            except Exception as err:
                await as_future(_throw(err))

        return wrapper()

    async def process_all(self, iterable: Iterable[Any]):
        assert self.__get_action is not None, f"`action` is required for {self.name}"

        if isinstance(iterable, Iterator):
            # process one by one
            return [await self.process_item(item) for item in iterable]

        # process all together
        return await asyncio.gather(
            *[self.process_item(item) for item in iterable],
            return_exceptions=True
        )

    async def process_item(self, item: Any):
        try:
            with branch({**await self.get_item_context(item)}):
                action = await self.__get_action(item)
                return await self.plugins.process_item(
                    partial(self.process_action, item, action), item
                )
        except Exception as err:
            logger.exception(f"{item}: {err}")
            raise

    async def process_action(self, item: Any, action: Any):
        if isinstance(action, Action):
            return await action()
        elif isinstance(action, Lazy):
            return await self.process_action(item, await action())
        elif isinstance(action, Iterator) or isgenerator(action):
            return [await self.process_action(item, subaction)
                    for subaction in action]
        elif isasyncgen(action):
            return [await self.process_action(item, subaction)
                    async for subaction in action]
        elif isinstance(action, Iterable):
            return await asyncio.gather(
                *[self.process_action(item, subaction)
                  for subaction in action]
            )
        # otherwise cosider action as a ready result
        return action

    async def get_item_context(self, item: Any) -> dict:
        return {self.context_key: item}

    async def get_application_context(self) -> dict:
        return {CTX_APPLICATION: self}

    def action(self, fn):
        self.__get_action_sig = signature(fn)
        self.__get_action = staticmethod(fn)
        return fn


def application(fn_or_name):
    def inner(fn, name=None):
        return Application(fn, name)
    return (partial(inner, name=fn_or_name)
            if isinstance(fn_or_name, str) else inner(fn_or_name))