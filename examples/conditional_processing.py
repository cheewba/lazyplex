#!/usr/bin/env python3
"""Test the conditional sequential processing example from README"""

import asyncio
from lazyplex import application


@application
async def conditional_processing():
    # Sequential processing with conditional logic
    for i in range(10):
        if i % 2 == 0:  # Only process even numbers
            await asyncio.sleep(0.1)  # Can include async logic
            yield i


@conditional_processing.action
async def process_even(item):
    result = f"Even number: {item}"
    print(result)
    return result


if __name__ == "__main__":
    print("Testing conditional sequential processing example...")
    results = conditional_processing.run_until_complete()
    print(f"Results: {results}")
    print("Conditional processing example completed successfully!")