import asyncio
import logging
import itertools
from contextlib import asynccontextmanager, AsyncExitStack
from functools import partial
from inspect import signature, isgenerator, Parameter, BoundArguments
from typing import (
    Any, Iterable, Iterator, Optional, Dict, Callable,
    Tuple, AsyncIterable, Generic, TypeVar
)

from .actions import Action, Lazy
from .constants import CTX_APPLICATION, CTX_COMPLETE_TASKS
from .context import branch, create_context, get_context
from .helpers import as_future, isasyncgen
from .plugin import Plugins
from .errors import ApplicationNotStarted, ExecutionError


# __all__ = ["Application", "return_value", "ApplicationAction"]

logger = logging.getLogger(__name__)
empty = object()

T = TypeVar("T")


async def _async_pass(data):
    return data


def return_value(value: Any):
    app = get_context()[CTX_APPLICATION]
    if not app:
        raise ExecutionError("Can't be used outside of application context")
    app.set_value(value)


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

    def bind_args(self, *args, **kwargs) -> BoundArguments:
        kw = self.sig.bind_partial(*args).arguments.copy()
        kw.update(kwargs)
        return self.sig.bind_partial(**kw)

    async def parse_args(self, *args, **kwargs) -> Tuple[Tuple, Dict]:
        bound = self.bind_args(*args, **kwargs)
        bound.apply_defaults()

        kwargs = {}
        for arg in self._arguments:
            val = await self.get_argument(arg, bound.arguments.get(arg, None))
            (bound.arguments if arg in bound.arguments else kwargs)[arg] = val

        return bound.args, {**bound.kwargs, **kwargs}

    def update_args(self, args: Tuple, kwargs: Dict,
                    *extra_args, **extra_kwargs) -> Tuple[Tuple, Dict]:
        bound = self.bind_args(*args, **kwargs)
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

    async def get_item_context(self, item: Any, index: Optional[int] = None) -> dict:
        return {
            self.context_key: item,
            f"{self.context_key}_index": index,
        }

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

    async def process_item(self, item: Any, *, plugins: Plugins, **kwargs):
        with branch({**await self.get_item_context(item, kwargs.pop('index', None))}):
            async def _process(_item):
                a, kw = await self.parse_args(_item, **kwargs)
                return await self._process_action(_item, await self.fn(*a, **kw))

            return await plugins.process_item(_process, item)

    def __call__(self, *args, **kwargs):
        ctx = get_context()
        app = ctx.get(CTX_APPLICATION) if ctx else None
        itm = ctx.get(self.context_key) if ctx else None
        if app is None or itm is not None:
            # if the method called outside of the app context,
            # or item context already initialized, call the action as a regular function
            return self.fn(*args, **kwargs)

        return self.process_item(*args, **kwargs)


class Application(Generic[T], ArgumentsMixin):
    name: str
    plugins: Plugins
    return_exceptions: bool
    action_class: T = ApplicationAction

    _actions: Dict[str, T]
    _arguments = Dict[str, Callable]
    _default_action: Optional[str] = None

    def __init__(
        self,
        initializer,
        *,
        name: Optional[str] = None,
        return_exceptions: bool = False,
        # don't iterate over items in action
        protected_items: bool = False,
    ) -> None:
        super().__init__(initializer)
        self.name = name or initializer.__name__
        self.plugins = Plugins()
        self.return_exceptions = return_exceptions
        self.protected_items = protected_items

        self._actions = {}
        self._arguments = {}

        self.__return_value = None

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

    def set_value(self, value):
        """ Set return value of application """
        self.__return_value = value

    async def run(self, *args, **kwargs):
        @asynccontextmanager
        async def _cleanup():
            try:
                yield
            finally:
                if len(tasks := ctx[CTX_COMPLETE_TASKS]):
                    await asyncio.gather(*[task() for task in tasks])

        def _raise_stop(result):
            raise StopIteration

        def _raise_error(error):
            raise error

        async with AsyncExitStack() as stack:
            await stack.enter_async_context(_cleanup())

            ctx = get_context()
            if ctx is None:
                ctx = stack.enter_context(create_context({}))
            await self.update_application_context(ctx)

            app_init, action = await self._run_initializer(*args, **kwargs)
            action_data, _send, _throw = None, None, None
            if isasyncgen(app_init):
                action_data = await anext(app_init)
                _send, _throw = app_init.asend, app_init.athrow
            elif isgenerator(app_init):
                action_data = next(app_init)
                _send, _throw = app_init.send, app_init.throw
            else:
                # in case of regular function, just process the returned result
                action_data = await as_future(app_init)
                _send, _throw = _raise_stop, _raise_error

            counter = itertools.count(start=1, step=1)
            while True:
                try:
                    result = None
                    if action is not None:
                        async def _process(action, data):
                            return await self.process_action_data(action, data, counter, **kwargs)
                        result = await self.plugins.process_action_data(_process, action, action_data)
                    action_data = await as_future(_send(result))
                except (StopIteration, StopAsyncIteration):
                    break
                except Exception as err:
                    action_data = await as_future(_throw(err))

        return self.__return_value

    async def process_action_data(self, action: T, data: Any,
                                  counter: Iterator[int] = None, **kwargs):
        counter = counter or itertools.count(start=1, step=1)
        async def wrapper(item, index):
            try:
                return await action(item, plugins=self.plugins, index=index, **kwargs)
            except Exception as e:
                if self.return_exceptions:
                    return e
                raise e

        tasks = None
        if not self.protected_items:
            if isinstance(data, AsyncIterable):
                tasks = [asyncio.create_task(wrapper(item, next(counter)))
                         async for item in data]
            elif isinstance(data, Iterable):
                tasks = [asyncio.create_task(wrapper(item, next(counter)))
                         for item in data]

        if tasks is None:
            # if no tasks were created, process data as a single item
            return await wrapper(data, next(counter))

        return await asyncio.gather(*tasks, return_exceptions=self.return_exceptions)

    def __call__(self, *args, **kwargs):
        return self.run(*args, **kwargs)

    def action_from_args(self, *args, **kwargs) -> Tuple[str, Optional[ApplicationAction]]:
        bound = self.bind_args(*args, **kwargs)
        bound.apply_defaults()

        action = bound.arguments.get('action', empty)
        if not action or action is empty:
            action = self._default_action
        return (name := action or ""), self._actions.get(name)

    async def _run_initializer(
        self, *args, **kwargs
    ) -> Tuple[Any, T]:
        action_name, action = self.action_from_args(*args, **kwargs)
        if action is not None:
            if action_name not in self._actions:
                raise TypeError(f"Application action `{action or ''}` is unknown.")
            args, kwargs = self.update_args(args, kwargs, action=action_name)

        a, kw = await self.parse_args(*args, **kwargs)
        return (self.fn(*a, **kw), action)

    async def update_application_context(self, ctx: Dict) -> dict:
        ctx[CTX_APPLICATION] = self
        ctx[CTX_COMPLETE_TASKS] = []

    def action(self, name: str, *, default: bool = False): ...
    def action(self, fn: Callable): ...  # noqa: F811
    def action(self, name_or_fn=None, *, default=False):  # noqa: F811
        name = name_or_fn
        def inner(fn: Callable):
            acion_name = name or fn.__name__
            self._actions[acion_name] = self.action_class(fn)
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
    protected_items: bool = False,
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