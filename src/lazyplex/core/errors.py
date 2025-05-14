class LazyplexError(Exception):
    pass


class ApplicationNotStarted(LazyplexError):
    pass


class ExecutionError(LazyplexError):
    pass