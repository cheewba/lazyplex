from contextvars import ContextVar
from contextlib import contextmanager
from enum import StrEnum
from typing import Tuple, Any, Generator

__all__ = ['get_context', 'ContextScope']

empty = object()


class ContextScope(StrEnum):
    application = "application"
    action = "action"


class ApplicationContext(dict):
    def unpack(self, *keys, default=empty) -> Tuple[Any]:
        return tuple(self[key] if default is empty else self.get(key, default)
                     for key in keys)

    def __setitem__(self, key, item):
        branch = _branch_context.get(None)
        if (branch is not None
                and (key in branch or not super().__contains__(key))):
            branch[key] = item
            return
        super().__setitem__(key, item)

    def __getitem__(self, key):
        branch = _branch_context.get(None)
        if branch:
            try:
                return branch[key]
            except KeyError:
                pass
        return super().__getitem__(key)

    def __delitem__(self, key):
        del self.__dict__[key]

    def __len__(self):
        branch = _branch_context.get(None)
        return super().__len__() + len(branch or {})

    def __contains__(self, item):
        branch = _branch_context.get(None)
        return item in (branch or {}) or super().__contains__(item)

    def __iter__(self):
        return iter(
            set((_branch_context.get(None) or {}).keys()) &
            set(super().keys())
        )

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def setdefault(self, key, default=None):
        if (key not in self):
            self[key] = default
        return self[key]

    def get_scope(self) -> ContextScope:
        branch = _branch_context.get(None)
        if branch:
            return ContextScope.action
        return ContextScope.application


def get_context() -> ApplicationContext:
    return _app_context.get(None)


@contextmanager
def create_context(ctx: dict = None) -> Generator["ApplicationContext", None, None]:
    token = _app_context.set(ApplicationContext(ctx or {}))
    try:
        yield get_context()
    finally:
        _app_context.reset(token)


@contextmanager
def branch(ctx: dict = None)-> Generator["ApplicationContext", None, None]:
    token = _branch_context.set(ctx or {})
    try:
        yield get_context()
    finally:
        _branch_context.reset(token)


_app_context = ContextVar('applicationContext')
_branch_context = ContextVar('branchContext')
