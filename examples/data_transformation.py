#!/usr/bin/env python3
"""Test the data transformation example from README"""

import asyncio
from lazyplex import application, apply_plugins
from lazyplex.plugins import progress_bar

# Sample data
sample_data = [
    {"id": 1, "value": 10},
    {"id": 2, "value": 20},
    {"id": 3, "value": 30}
]

@application
async def process_data():
    async with apply_plugins(progress_bar(len(sample_data))):
        return sample_data


@process_data.action
async def transform_item(item):
    await asyncio.sleep(0.1)  # Simulate processing time

    result = {
        "id": item["id"],
        "processed_value": item["value"] * 2,
        "timestamp": asyncio.get_event_loop().time()
    }
    print(f"Transformed item {item['id']}: {item['value']} -> {result['processed_value']}")
    return result


if __name__ == "__main__":
    print("Testing data transformation example...")
    results = process_data.run_until_complete()
    print(f"Results: {results}")
    print("Data transformation example completed successfully!")