from contextlib import asynccontextmanager, AsyncExitStack
from typing import Any

from .context import get_context

__all__ = ["Plugin", "apply_plugins"]


class Plugin:
    async def process_action(self, process, action):
        return await process()

    async def process_item(self, process, item):
        return await process()


class StackItem:
    def __init__(self, fn, bind_to=None) -> None:
        self.fn = staticmethod(fn)
        self.bind_to = bind_to

    def __call__(self, resolve, *args, **kwargs):
        return self.fn(self.bind_to or resolve, *args, **kwargs)


class Stack:
    def __init__(self) -> None:
        self._top = None

    def push(self, fn):
        self._top = StackItem(fn, self._top)

    def pop(self):
        item, self._top = self._top, self._top.bind_to
        return item

    async def __call__(self, resolve, *args: Any, **kwargs: Any) -> Any:
        return await (self._top(resolve, *args, **kwargs) if self._top else resolve())


class Plugins:
    methods = ('process_action', 'process_item')

    def __init__(self) -> None:
        for method in self.methods:
            setattr(self, f"_{method}", Stack())

    @asynccontextmanager
    async def _to_context(self, loader):
        try:
            yield await anext(loader)
        finally:
            try:
                await anext(loader)
            except StopAsyncIteration:
                pass

    @asynccontextmanager
    async def apply(self, *loaders):
        async with AsyncExitStack() as stack:
            to_stack = stack.enter_async_context
            plugins = [await to_stack(self._to_context(plugin)) for plugin in loaders]

            for middleware in plugins[::-1]:
                for method in self.methods:
                    getattr(self, f"_{method}").push(getattr(middleware, method))

            try:
                yield
            finally:
                for middleware in plugins[::-1]:
                    for method in self.methods:
                        getattr(self, f"_{method}").pop()

    async def process_action(self, process, action):
        return await self._process_action(process, action)

    async def process_item(self, process, item):
        return await self._process_item(process, item)


@asynccontextmanager
async def apply_plugins(*loaders):
    app, *_ = get_context().unpack('_application')
    async with app.plugins.apply(*loaders):
        yield
