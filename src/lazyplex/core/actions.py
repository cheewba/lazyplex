import asyncio
from functools import partial
from inspect import signature, Signature, BoundArguments
from typing import Callable, Protocol, Type, Generic, TypedDict, TypeVar, Optional

from .helpers import as_future
from .context import get_context


Ctx = TypeVar('Ctx', bound=TypedDict)

class RunnerType(Protocol, Generic[Ctx]):
    def __call__(self, *args, **kwargs) -> None: ...


class Lazy:
    def __init__(self, fn, *args, **kwargs) -> None:
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self._call_queue = [(fn, args, kwargs)]

    async def __call__(self):
        async def to_args(args):
            return await asyncio.gather(
                *(asyncio.ensure_future(value()) if isinstance(value, Lazy)
                else as_future(value) for value in args)
            )

        value = self
        for (fn, args, kwargs) in self._call_queue:
            new_args = (await to_args(args)) if args else []
            new_kwargs = {}
            if (kwargs):
                kw_keys, kw_values = zip(*kwargs.items())
                kw_values = await to_args(kw_values)
                new_kwargs = dict(zip(kw_keys, kw_values))
            if (isinstance(fn, str)):
                fn = getattr(value, fn)

            value = await as_future(fn(*new_args, **new_kwargs))
        return value

    def clone(self, cls):
        clone = cls(self.fn, self.args, self.kwargs)
        clone._call_queue = [*self._call_queue]
        return clone


def as_lazy(fn) -> Callable:
    def inner(*args, **kwargs) -> Lazy:
        return Lazy(fn, *args, **kwargs)
    return inner


class LazyArg(Lazy):
    pass


class Action(Generic[Ctx]):
    __runner: Optional[RunnerType[Ctx]] = None
    __runner_name: Optional[str] = ""
    __signature: Optional[Signature] = None
    __bound_sig: Optional[BoundArguments] = None

    def __init_subclass__(cls, runner: RunnerType[Ctx] = None, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        if runner is not None:
            cls.__runner_name = runner.__name__
            cls.__runner = staticmethod(runner)
            cls.__signature = signature(runner)

    def __init__(self, *args, **kwargs) -> None:
        assert self.__runner is not None, "Aciton without runner can't be initialized"

        self.args = args
        self.kwargs = kwargs

    async def __call__(self) -> None:
        # if not isinstance(self, MergedAction):
        #     print(bound)
        app, *_ = get_context().unpack('_application')
        bound = await self.__get_bound_sig()

        async def wrapper():
            return await as_future(self.__runner(*bound.args, **bound.kwargs))

        executable = wrapper
        if not isinstance(self, MergedAction):
            executable = partial(app.plugins.process_action, wrapper, self)
        return await executable()

    def __str__(self) -> str:
        if not self.__bound_sig:
            return self.__runner_name
        return f"{self.__runner_name}{self.__bound_sig}"

    def __rshift__(self, other: "Action") -> "Action":
    # def __ror__(self, other: "Action") -> "Action":
        async def runner() -> None:
            await self()
            await other()

        class ShiftAction(MergedAction, runner=runner):
            pass

        return ShiftAction()

    async def __get_bound_sig(self):
        if not self.__bound_sig:
            args = [(await value()) if isinstance(value, Lazy) else value for value in self.args]
            kwargs = {key: ((await value()) if isinstance(value, Lazy) else value)
                        for key, value in self.kwargs.items()}

            # Use for arg() operator
            bound = self.__signature.bind(*args, *kwargs)
            bound.apply_defaults()
            self.__bound_sig = bound

        return self.__bound_sig


class MergedAction(Action):
    pass


def action(fn: RunnerType[Ctx]) -> Type[Action[Ctx]]:
    class RunnerAction(Action, runner=fn):
        pass
    return RunnerAction


def _lazy_special_wrapper(name):
    def wrapper(self, *args, **kwargs):
        if (name in {'__getattribute__'} and name.startswith('_')):
            return object.__getattribute__(self, *args, **kwargs)
        self._call_queue.append([name, args, kwargs])
        return self
    return wrapper


for method in [
    '__eq__', '__ne__', '__lt__', '__gt__', '__le__', '__ge__',
    '__pos__', '__neg__', '__abs__', '__invert__', '__round__', '__floor__',
    '__ceil__', '__trunc__', '__add__', '__sub__', '__mul__', '__floordiv__',
    '__div__', '__truediv__', '__mod__', '__divmod__', '__pow__', '__lshift__',
    '__rshift__', '__and__', '__or__', '__xor__', '__radd__', '__rsub__',
    '__rmul__', '__rfloordiv__', '__rdiv__', '__rtruediv__', '__rmod__', '__rdivmod__',
    '__rpow__', '__rlshift__', '__rrshift__', '__rand__', '__ror__', '__rxor__',
    '__iadd__', '__isub__', '__imul__', '__ifloordiv__', '__idiv__', '__itruediv__',
    '__imod__', '__ipow__', '__ilshift__', '__irshift__', '__iand__', '__ior__',
    '__ixor__', '__int__', '__long__', '__float__', '__complex__', '__oct__',
    '__hex__', '__index__', '__trunc__', '__coerce__', '__str__', '__repr__',
    '__hash__', '__nonzero__', '__dir__', '__sizeof__', '__getattribute__',
    '__len__', '__getitem__', '__iter__', '__reversed__', '__contains__',
    '__missing__', '__instancecheck__', '__subclasscheck__',
]:
    setattr(Lazy, method, _lazy_special_wrapper(method))
