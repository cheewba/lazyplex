import asyncio
import logging
from contextlib import ExitStack
from functools import partial
from inspect import signature, Signature, isgenerator
from typing import Any, Iterable, Iterator, Optional, Dict, Callable, Tuple

from .actions import Action, Lazy
from .constants import CTX_APPLICATION, CTX_COMPLETE_TASKS
from .context import branch, create_context, get_context
from .helpers import as_future, dummy, isasyncgen
from .plugin import Plugins
from .errors import ApplicationNotStarted

logger = logging.getLogger(__name__)
empty = object()


async def _async_pass(data):
    return data


class _ApplicationAction:
    def __init__(self, fn) -> None:
        self.fn = staticmethod(fn)
        self.sig = signature(fn)

    @property
    def context_key(self):
        name = 'item'
        if self.sig:
            args = list(self.sig.parameters.keys())
            if args:
                name = args[0]
        return name

    async def get_item_context(self, item: Any) -> dict:
        return {self.context_key: item}

    async def _process_action(self, item: Any, action: Any):
        result = action
        if isinstance(action, Action):
            result = await action()
        elif isinstance(action, Lazy):
            result = await self._process_action(item, await action())
        elif isinstance(action, Iterator) or isgenerator(action):
            result = [(await self._process_action(item, subaction))
                      if isinstance(subaction, (Action, Lazy)) else subaction
                      for subaction in action]
        elif isasyncgen(action):
            result = [(await self._process_action(item, subaction))
                      if isinstance(subaction, (Action, Lazy)) else subaction
                      async for subaction in action]
        elif isinstance(action, Iterable) and not isinstance(action, dict):
            result = await asyncio.gather(
                *[self._process_action(item, subaction)
                  if isinstance(subaction, (Action, Lazy)) else _async_pass(subaction)
                for subaction in action]
            )
        # otherwise cosider action as a ready result
        return result

    async def _process_item(self, item: Any, *, plugins: Plugins, **kwargs):
        with branch({**await self.get_item_context(item)}):
            async def _process():
                return await self._process_action(item, await self.fn(item, **kwargs))
            return await plugins.process_item(_process, item)
    __call__ = _process_item


class Application:
    name: str
    plugins: Plugins
    return_exceptions: bool

    _actions: Dict[str, _ApplicationAction]
    _arguments = Dict[str, Callable]
    _deafult_action: Optional[str] = None

    __initializer = None
    __initializer_sig: Signature

    def __init__(
        self,
        initializer,
        *,
        name: Optional[str] = None,
        return_exceptions: bool = False
    ) -> None:
        self.name = name or initializer.__name__
        self.plugins = Plugins()
        self.return_exceptions = return_exceptions

        self._actions = {}
        self._arguments = {}
        self.__initializer_sig = signature(initializer)
        self.__initializer = staticmethod(initializer)

    def run_until_complete(self, *args, **kwargs):
        asyncio.get_event_loop().run_until_complete(self(*args, **kwargs))

    def add_complete_tasks(self, fn, *args, **kwargs):
        ctx = get_context()
        if ctx is None:
            raise ApplicationNotStarted("Can't add task to unstarted application")
        ctx[CTX_COMPLETE_TASKS].append(partial(fn, *args, **kwargs))

    async def run(self, *args, **kwargs):
        with ExitStack() as stack:
            ctx = get_context()
            if ctx is None:
                ctx = stack.enter_context(create_context({}))
            await self.update_application_context(ctx)

            app_init, action = await self._run_initializer(*args, **kwargs)
            if isasyncgen(app_init):
                iterable = await anext(app_init)
                _send, _throw = app_init.asend, app_init.athrow
            elif isgenerator(app_init):
                iterable = next(app_init)
                _send, _throw = as_future(app_init.send), as_future(app_init.throw)
            else:
                iterable = await as_future(app_init)
                _send, _throw = as_future(dummy), as_future(dummy)

            # TODO: case if there's no action and result returned
            # TODO: should app return exceptions or raise if any action is failed ?

            try:
                result = await self.process_all(action, iterable)
                finalize = _send(result)
            except Exception as err:
                finalize = _throw(err)

            try:
                await finalize
            except (StopIteration, StopAsyncIteration):
                pass
            finally:
                if len(tasks := ctx[CTX_COMPLETE_TASKS]):
                    await asyncio.gather(*[task() for task in tasks])

    def __call__(self, *args, **kwargs):
        return self.run(*args, **kwargs)

    def __getattr__(self, name) -> Any:
        if name in self.__initializer_sig.parameters:
            return self._argument_decorator(name)

        raise AttributeError(
            f"Attribute '{name}' must be added as application initializer's argument, "
            f"to be able to use it as the application function decorator"
        )

    def _argument_decorator(self, name):
        def inner(fn):
            self._arguments[name] = fn
            return fn
        return inner

    async def _run_initializer(
        self, *args, **kwargs
    ) -> Tuple[Any, _ApplicationAction]:
        init_kwargs = {}
        bound = self.__initializer_sig.bind_partial(*args, **kwargs)

        action = bound.arguments.get('action')
        if action and not action in self._actions:
            raise TypeError(f"Application action '{action}' is unknown.")
        action = action or self._deafult_action
        if action:
            init_kwargs['action'] = action

        for arg in self.__initializer_sig.parameters:
            val = bound.arguments.get(arg, empty)
            if val is empty and arg in self._arguments:
                val = await self.get_argument(arg)
            if val is not empty:
                init_kwargs[arg] = val

        return (self.__initializer(**init_kwargs),
                self._actions.get(action))

    async def process_all(self, action: _ApplicationAction,
                          iterable: Iterable[Any]):
        if isinstance(iterable, Iterator):
            # process one by one
            async def wrapper(item):
                try:
                    return await action(item, plugins=self.plugins)
                except Exception as e:
                    if self.return_exceptions:
                        return e
                    raise e
            return [await wrapper(item) for item in iterable]

        # process all together
        return await asyncio.gather(
            *[action(item, plugins=self.plugins) for item in iterable],
            return_exceptions=self.return_exceptions
        )

    async def update_application_context(self, ctx: Dict) -> dict:
        ctx[CTX_APPLICATION] = self
        ctx[CTX_COMPLETE_TASKS] = []

    async def get_argument(self, name: str) -> Any:
        return await as_future(self._arguments[name]())

    def argument(self, name: str): ...
    def argument(self, fn: Callable): ...  # noqa: F811
    def argument(self, name_or_fn=None):  # noqa: F811
        name = name_or_fn
        if isinstance(name_or_fn, Callable):
            name = name_or_fn.__name__
        if name in self.__initializer_sig.parameters:
            return self._argument_decorator(name)

        raise AttributeError(
            f"Attribute '{name}' must be added as application initializer's argument"
        )

    def action(self, name: str, *, default: bool = False): ...
    def action(self, fn: Callable): ...  # noqa: F811
    def action(self, name_or_fn=None, *, default=False):  # noqa: F811
        name = name_or_fn
        def inner(fn: Callable):
            self._actions[name or fn.__name__] = _ApplicationAction(fn)
            if default or self._deafult_action is None:
                self._deafult_action = name
            return fn

        if isinstance(name_or_fn, Callable):
            name = name_or_fn.__name__
            return inner(name_or_fn)
        return inner


def application(fn: Callable) -> Application: ...
def application(  # noqa: F811
    name: Optional[str] = None,
    *,
    return_exception: bool = False,
    application_class: Optional[type] = None
) -> Callable[[Callable], Application]: ...
def application(*args, **kwargs):  # noqa: F811
    def inner(fn, **kwargs):
        return (kwargs.pop('application_class', None) or Application)(fn, **kwargs)

    if args and isinstance(args[0], Callable):
        return inner(args[0])

    def wrapper(name=None, **kwargs):
        return partial(inner, name=name, **kwargs)
    return wrapper(*args, **kwargs)