import asyncio
import logging
from contextlib import ExitStack
from functools import partial
from inspect import signature, isgenerator, Parameter
from typing import (
    Any, Iterable, Iterator, Optional, Dict, Callable, Tuple,
    AsyncIterable, AsyncIterator, Union,
)

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


class ArgumentsMixin:
    def __init__(self, fn) -> None:
        self.fn = staticmethod(fn)
        self.sig = signature(fn)

        self._arguments = {}

    def _has_argument(self, name, throw=False):
        parameters: Dict[str, Parameter] = self.sig.parameters
        has_argument = (
            # there's an explicit argument in signature
            name in parameters
            # or signature has a dict of keyword arguments
            or len([par for par in parameters.values()
                    if par.kind == Parameter.VAR_KEYWORD])
        )
        if not has_argument and throw:
            raise AttributeError(
                f"Attribute '{name}' must be added as argument or **kwargs to {self.fn.__name__} function, "
                f"to be processed by `argument` decorator"
            )
        return has_argument

    def __getattr__(self, name) -> Any:
        if self._has_argument(name, throw=True):
            return self._argument_decorator(name)

    def _argument_decorator(self, name):
        def inner(fn):
            self._arguments[name] = fn
            return fn
        return inner

    async def get_argument(self, name: str, value: any) -> Any:
        return await as_future(self._arguments[name](value))

    def argument(self, name: str): ...
    def argument(self, fn: Callable): ...  # noqa: F811
    def argument(self, name_or_fn=None):  # noqa: F811
        name = name_or_fn
        if isinstance(name_or_fn, Callable):
            name = name_or_fn.__name__

        if self._has_argument(name, throw=True):
            return self._argument_decorator(name)

    async def parse_args(self, *args, **kwargs) -> Tuple[Tuple, Dict]:
        bound = self.sig.bind_partial(*args, **kwargs)
        bound.apply_defaults()

        kwargs = {}
        for arg in self._arguments:
            val = await self.get_argument(arg, bound.arguments.get(arg, None))
            (bound.arguments if arg in bound.arguments else kwargs)[arg] = val

        return bound.args, {**bound.kwargs, **kwargs}

    def update_args(self, args: Tuple, kwargs: Dict,
                    *extra_args, **extra_kwargs) -> Tuple[Tuple, Dict]:
        bound = self.sig.bind_partial(*args, **kwargs)
        for arg, value in self.sig.bind_partial(*extra_args).arguments.items():
            bound.arguments[arg] = value

        kwargs = {}
        for key, value in self.sig.bind_partial(**extra_kwargs).kwargs.items():
            if key in bound.arguments:
                bound.arguments[key] = value
            kwargs[key] = value

        return bound.args, {**bound.kwargs, **kwargs}


class ApplicationAction(ArgumentsMixin):
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
                a, kw = await self.parse_args(item, **kwargs)
                return await self._process_action(item, await self.fn(*a, **kw))
            return await plugins.process_item(_process, item)
    __call__ = _process_item


class Application(ArgumentsMixin):
    name: str
    plugins: Plugins
    return_exceptions: bool

    _actions: Dict[str, ApplicationAction]
    _arguments = Dict[str, Callable]
    _default_action: Optional[str] = None

    def __init__(
        self,
        initializer,
        *,
        name: Optional[str] = None,
        return_exceptions: bool = False
    ) -> None:
        super().__init__(initializer)
        self.name = name or initializer.__name__
        self.plugins = Plugins()
        self.return_exceptions = return_exceptions

        self._actions = {}
        self._arguments = {}

    @property
    def default_actions(self) -> Optional[str]:
        return self._default_action

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
                _send, _throw = app_init.send, app_init.throw
            else:
                iterable = await as_future(app_init)
                _send, _throw = dummy, dummy

            # TODO: case if there's no action and result returned
            # TODO: should app return exceptions or raise if any action is failed ?

            try:
                result = await self.process_all(action, iterable)
                finalize = as_future(_send(result))
            except Exception as err:
                finalize = as_future(_throw(err))

            try:
                await finalize
            except (StopIteration, StopAsyncIteration):
                pass
            finally:
                if len(tasks := ctx[CTX_COMPLETE_TASKS]):
                    await asyncio.gather(*[task() for task in tasks])

    def __call__(self, *args, **kwargs):
        return self.run(*args, **kwargs)

    async def _run_initializer(
        self, *args, **kwargs
    ) -> Tuple[Any, ApplicationAction]:
        bound = self.sig.bind_partial(*args, **kwargs)
        bound.apply_defaults()

        action = bound.arguments.get('action', empty)
        if not action or action is empty:
            action = self._default_action
        if not action or action not in self._actions:
            raise TypeError(f"Application action `{action or ''}` is unknown.")
        bound.arguments['action'] = action

        kwargs = {}
        for arg in self._arguments:
            val = await self.get_argument(arg, bound.arguments.get(arg, None))
            (bound.arguments if arg in bound.arguments else kwargs)[arg] = val

        return (self.fn(*bound.args, **{**bound.kwargs, **kwargs}),
                self._actions.get(action))

    async def process_all(self, action: ApplicationAction,
                          iterable: Union[Iterable[Any], AsyncIterable[Any]]):
        async def wrapper(item):
            try:
                return await action(item, plugins=self.plugins)
            except Exception as e:
                if self.return_exceptions:
                    return e
                raise e

        if isinstance(iterable, Iterator):
            # process one by one
            return [await wrapper(item) for item in iterable]
        elif isinstance(iterable, AsyncIterator):
            # process one by one
            return [await wrapper(item) async for item in iterable]

        # process all together
        return await asyncio.gather(
            *[wrapper(item) for item in iterable],
            return_exceptions=self.return_exceptions
        )

    async def update_application_context(self, ctx: Dict) -> dict:
        ctx[CTX_APPLICATION] = self
        ctx[CTX_COMPLETE_TASKS] = []

    def action(self, name: str, *, default: bool = False): ...
    def action(self, fn: Callable): ...  # noqa: F811
    def action(self, name_or_fn=None, *, default=False):  # noqa: F811
        name = name_or_fn
        def inner(fn: Callable):
            acion_name = name or fn.__name__
            self._actions[acion_name] = ApplicationAction(fn)
            if default or self._default_action is None:
                self._default_action = acion_name
            return self._actions[acion_name]

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