#!/usr/bin/env python3
"""Test the context management example from README"""

from lazyplex import application, get_context, return_value

@application
async def context_example():
    ctx = get_context()
    ctx['config'] = {'multiplier': 3}

    return range(5)

@context_example.action
async def process_with_context(item):
    ctx = get_context()

    # Access application instance (application-level)
    app = ctx['_application']
    print(f"Processing item {item} with app: {type(app).__name__}")

    # Application-level data (common for all items)
    shared_config = ctx.get('config', {'multiplier': 2})

    # Set return value for entire application (application-level)
    # Note: This sets the final return value but doesn't break processing of other items
    if item == 3:
        return_value("Found item 3!")
        print("Set return value to 'Found item 3!'")

    result = item * shared_config['multiplier']
    print(f"Item {item} -> {result}")
    return result


if __name__ == "__main__":
    print("Testing context management example...")
    results = context_example.run_until_complete()
    print(f"Results: {results}")
    print("Context management example completed successfully!")