#!/usr/bin/env python3
"""Test the argument processing example from README"""

from lazyplex import application

@application
async def with_args(multiplier=2):
    print(f'application multiplier: {multiplier}')
    return range(10)


@with_args.argument
def multiplier(value):
    print("multiplier processing for application")
    return value * 2


@with_args.action
async def multiply_item(item, multiplier):
    result = item * multiplier
    print(f"Item {item} * {multiplier} = {result}")
    return result


@multiply_item.argument('multiplier')
def action_multiplier(value):
    print("multiplier processing for action")
    return (value or 2) / 2


if __name__ == "__main__":
    print("Testing argument processing example...")

    # Test with default multiplier
    print("With default multiplier (2):")
    results1 = with_args.run_until_complete()
    print(f"Results: {results1[:5]}...")  # Show first 5 results

    # Test with custom multiplier
    print("\nWith custom multiplier (3):")
    results2 = with_args.run_until_complete(multiplier=3)
    print(f"Results: {results2[:5]}...")  # Show first 5 results

    print("Argument processing example completed successfully!")