from contextlib import asynccontextmanager, AsyncExitStack
from typing import Any, AsyncIterator, TYPE_CHECKING, Callable, Awaitable

from .context import get_context
from .helpers import deprecated
if TYPE_CHECKING:
    from .application import Action

__all__ = ["Plugin", "apply_plugins"]


class Plugin:
    @deprecated
    async def process_action(self, process, action):
        return await process()

    async def process_item(self, process: Callable[[Any], Awaitable], item: Any):
        return await process(item)

    async def process_action_data(self, process: Callable[["Action", Any], Awaitable],
                                  action: "Action", data: Any):
        return await process(action, data)


class StackItem:
    def __init__(self, fn, bind_to=None) -> None:
        self.fn = staticmethod(fn)
        self.bind_to = bind_to

    def __call__(self, resolve, *args, **kwargs):
        def _resolve(*a, **kw):
            if self.bind_to:
                return self.bind_to(resolve, *a, **kw)
            return resolve(*a, **kw)
        return self.fn(_resolve, *args, **kwargs)


class Stack:
    def __init__(self) -> None:
        self._top = None

    def push(self, fn):
        self._top = StackItem(fn, self._top)

    def pop(self):
        item, self._top = self._top, self._top.bind_to
        return item

    async def __call__(self, resolve, *args: Any, **kwargs: Any) -> Any:
        return await (self._top(resolve, *args, **kwargs) if self._top else resolve(*args, **kwargs))


class Plugins:
    methods = (
        'process_action',
        'process_item',
        'process_action_data',
    )

    def __init__(self) -> None:
        self._plugins = []
        for method in self.methods:
            setattr(self, f"_{method}", Stack())

    @property
    def active_plugins(self):
        return self._plugins.copy()

    @asynccontextmanager
    async def _to_context(self, loader):
        if isinstance(loader, AsyncIterator):
            try:
                yield await anext(loader)
            finally:
                try:
                    await anext(loader)
                except StopAsyncIteration:
                    pass
        else:
            yield loader

    @asynccontextmanager
    async def apply(self, *loaders):
        async with AsyncExitStack() as stack:
            to_stack = stack.enter_async_context
            plugins = [await to_stack(self._to_context(plugin)) for plugin in loaders]

            for middleware in plugins[::-1]:
                for method in self.methods:
                    getattr(self, f"_{method}").push(getattr(middleware, method))
                self._plugins.append(middleware)

            try:
                yield
            finally:
                for middleware in plugins[::-1]:
                    for method in self.methods:
                        getattr(self, f"_{method}").pop()
                self._plugins.pop()

    @deprecated
    async def process_action(self, process, action):
        return await self._process_action(process, action)

    async def process_action_data(self, process, action, data):
        return await self._process_action_data(process, action, data)

    async def process_item(self, process, item):
        return await self._process_item(process, item)


@asynccontextmanager
async def apply_plugins(*loaders):
    app, *_ = get_context().unpack('_application')
    async with app.plugins.apply(*loaders):
        yield
