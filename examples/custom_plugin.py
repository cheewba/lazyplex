#!/usr/bin/env python3
"""Test the custom plugin example from README"""

import logging
from lazyplex import Plugin, application, apply_plugins

# Set up logging to see the plugin output
logging.basicConfig(level=logging.INFO)

class LoggingPlugin(Plugin):
    def __init__(self, logger_name="lazyplex"):
        self.logger = logging.getLogger(logger_name)

    async def process_item(self, process, item):
        self.logger.info(f"Processing item: {item}")
        try:
            result = await process(item)
            self.logger.info(f"Completed item: {item} -> {result}")
            return result
        except Exception as e:
            self.logger.error(f"Failed item: {item} - {e}")
            raise


@application
async def logged_processing():
    async with apply_plugins(LoggingPlugin()):
        return range(5)


@logged_processing.action
async def process_with_logging(item):
    if item == 3:
        raise ValueError("Simulated error")
    return item * 2


if __name__ == "__main__":
    print("Testing custom plugin example...")
    try:
        results = logged_processing.run_until_complete()
        print(f"Results: {results}")
    except ValueError as e:
        print(f"Caught expected error: {e}")
    print("Custom plugin example completed!")