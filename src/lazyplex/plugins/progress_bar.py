import logging
import sys
from contextlib import contextmanager

from colorama import Fore
from tqdm import tqdm
from tqdm.contrib import DummyTqdmFile
from tqdm.contrib.logging import logging_redirect_tqdm

from .. import get_context
from .. import Plugin

logger = logging.getLogger(__name__)

__all__ = ['progress_bar']


@contextmanager
def std_out_err_redirect_tqdm():
    orig_out_err = sys.stdout, sys.stderr
    try:
        sys.stdout, sys.stderr = map(DummyTqdmFile, orig_out_err)
        yield orig_out_err[0]
    # Relay exceptions
    except Exception as exc:
        raise exc
    # Always restore sys.stdout/err if necessary
    finally:
        sys.stdout, sys.stderr = orig_out_err


class ProgressBar(Plugin):
    async def process_item(self, process, item):
        ctx = get_context()
        try:
            result = await process()
            ctx['progress'].update()
            return result
        except Exception as e:
            logger.error(Fore.RED + f"{item}: {str(e)}")
            raise


async def progress_bar(total):
    ctx = get_context()
    with logging_redirect_tqdm(), std_out_err_redirect_tqdm() as orig_stdout:
        ctx['progress'] = tqdm(total, desc="Progress", file=orig_stdout, dynamic_ncols=True)
        try:
            yield ProgressBar()
        finally:
            ctx['progress'].close()