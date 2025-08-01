#!/usr/bin/env python3
"""Test the progress bar example from README"""

import asyncio
from lazyplex import application, apply_plugins
from lazyplex.plugins import progress_bar


@application
async def progress_example():
    async with apply_plugins(progress_bar(5)):
        yield range(5)


@progress_example.action
async def process_with_progress(item):
    await asyncio.sleep(0.5)  # Simulate work
    return item * 2


if __name__ == "__main__":
    print("Testing progress bar example...")
    results = progress_example.run_until_complete()
    print(f"Results: {results}")
    print("Progress bar example completed successfully!")