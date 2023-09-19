import asyncio

from lazyplex import application, apply_plugins
from lazyplex.plugins import progress_bar

@application
async def example():
    # there're 2 ways how to return items to process:
    # 1. if Iterable (list, set, tuple) of items returned,
    #     processing will start for all items at the same time
    # 2. if Iterator returned (e.g. iter(list)), items will be processed one by one
    count = 10
    async with apply_plugins(progress_bar(count)):
        yield iter(range(1, count + 1))
    # post-processing may go here

    # in case there's no postporcessing,
    # it's possible just return iterable/iterator:
    # return range(1, 10)


@example.action
async def action(value):
    print(f"Iteration {value}")
    # sleep to make progress bar changes notable
    await asyncio.sleep(1)


if __name__ == '__main__':
    example.run_until_complete()