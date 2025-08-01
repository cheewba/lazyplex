#!/usr/bin/env python3
"""Test the sequential processing example from README"""

import asyncio
from lazyplex import application


@application
async def sequential_example():
    # Sequential processing - yield individual items
    for i in range(5):
        await asyncio.sleep(0.1)  # Can include async logic
        yield i


@sequential_example.action
async def process_sequential(item):
    result = item * 3
    print(f"Sequential processing item {item} -> {result}")
    return result


if __name__ == "__main__":
    print("Testing sequential processing example...")
    results = sequential_example.run_until_complete()
    print(f"Results: {results}")
    print("Sequential processing example completed successfully!")