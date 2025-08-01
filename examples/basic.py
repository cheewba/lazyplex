#!/usr/bin/env python3
"""Test the basic example from README"""

import asyncio
from lazyplex import application


@application
async def basic_example():
    return range(5)


@basic_example.action
async def process_item(item):
    await asyncio.sleep(0.1)  # Simulate async work
    return item * 2


if __name__ == "__main__":
    print("Testing basic example...")
    results = basic_example.run_until_complete()
    print(f"Results: {results}")
    print("Basic example completed successfully!")