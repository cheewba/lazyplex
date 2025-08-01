# Lazyplex - Asynchronous Actions Multi-Processor Framework

## Overview

Lazyplex is a Python 3.11+ framework for building asynchronous data processing applications. It provides a decorator-based API for creating multi-step processing pipelines with built-in support for progress tracking and plugin extensibility.

**Key Characteristics:**
- Asynchronous processing built on asyncio
- Decorator-based API (`@application`, `@action`)
- Support for both parallel and sequential processing patterns
- Plugin system for extensibility
- Context management for complex workflows
- Built-in progress tracking with tqdm integration

## Installation

```bash
pip install -e git+https://github.com/cheewba/lazyplex.git#egg=lazyplex
```

## Core API Reference

### Main Decorators

#### `@application`
Decorator for creating the main application entry point.

**Parameters:**
- `name`: Optional application name
- `return_exceptions`: If True, exceptions are returned as results instead of raised
- `protected_items`: If True, forces sequential processing of single items

```python
from lazyplex import application

@application
async def my_app():
    # Return Iterable for parallel processing
    return [1, 2, 3, 4, 5]

@application(protected_items=True)
async def protected_app():
    # Forces single-item processing even for iterables
    return [1, 2, 3, 4, 5]
```

#### `@action`
Decorator for defining processing logic for each item.

```python
@my_app.action
async def process_item(item):
    # Process individual item
    result = await some_async_operation(item)
    return result
```

### Core Classes

#### `Application`
Main application class that orchestrates the processing pipeline.

**Methods:**
- `run_until_complete()` - Execute the application and return results
- `action` - Decorator property for defining actions

#### `Action`
Base class for processing actions.

#### `Plugin`
Base class for extending functionality.

```python
from lazyplex import Plugin

class CustomPlugin(Plugin):
    async def process_item(self, process, item):
        # Pre-processing
        result = await process(item)
        # Post-processing
        return result
```

### Core Functions

#### `apply_plugins(*plugins)`
Context manager for applying plugins to the processing pipeline.

```python
from lazyplex import apply_plugins
from lazyplex.plugins import progress_bar

@application
async def with_plugins():
    async with apply_plugins(progress_bar(10)):
        for i in range(10):
            yield i
```

#### `get_context()`
Access the current execution context.

```python
from lazyplex import get_context

@my_app.action
async def context_aware(item):
    ctx = get_context()
    # Access application context
    return item
```

#### `return_value(value)`
Set the return value for the entire application.

```python
from lazyplex import return_value

@my_app.action
async def early_return(item):
    if item == 42:
        return_value("Found the answer!")
    return item
```

## Processing Modes

### Parallel Processing (Default)
When you return an `Iterable` (list, tuple, set) or `AsyncIterable`, all items are processed concurrently:

```python
@application
async def parallel_app():
    return [1, 2, 3, 4, 5]  # All processed simultaneously

@application
async def parallel_iterator():
    return iter([1, 2, 3, 4, 5])  # Still parallel! Iterator is iterable
```

### Sequential Processing
For true sequential processing, you must yield individual items in a loop:

```python
@application
async def sequential_app():
    for item in [1, 2, 3, 4, 5]:
        yield item  # Each item processed one by one

@application
async def sequential_generator():
    for i in range(5):
        # Can include logic between yields
        await asyncio.sleep(0.1)
        yield i
```

### Protected Items Mode
Use `protected_items=True` to force single-item processing even for iterables:

```python
@application(protected_items=True)
async def protected_app():
    # This list will be processed as a single item, not iterated
    return [1, 2, 3, 4, 5]

@protected_app.action
async def process_list(entire_list):
    # entire_list is [1, 2, 3, 4, 5]
    return sum(entire_list)
```

## Built-in Plugins

### Progress Bar Plugin

```python
from lazyplex.plugins import progress_bar

@application
async def with_progress():
    count = 100
    async with apply_plugins(progress_bar(count)):
        for i in range(count):
            yield i
```

**Features:**
- Integrates with tqdm for progress visualization
- Handles stdout/stderr redirection
- Updates automatically as items are processed

## Complete Working Examples

### Basic Example (from examples/basic.py)

```python
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
    results = basic_example.run_until_complete()
    print(f"Results: {results}")
```

### Progress Bar Example (from examples/progress_bar.py)

```python
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
    results = progress_example.run_until_complete()
    print(f"Results: {results}")
```

### Sequential Processing Example (from examples/sequential.py)

```python
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
    results = sequential_example.run_until_complete()
    print(f"Results: {results}")
```

### Data Processing Pipeline (from examples/data_transformation.py)

```python
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
    results = process_data.run_until_complete()
    print(f"Results: {results}")
```

### Custom Plugin Example (from examples/custom_plugin.py)

```python
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
    try:
        results = logged_processing.run_until_complete()
        print(f"Results: {results}")
    except ValueError as e:
        print(f"Caught expected error: {e}")
```

### Conditional Processing Example (from examples/conditional_processing.py)

```python
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
    results = conditional_processing.run_until_complete()
    print(f"Results: {results}")
```

### File Processing Example (from examples/file_processing.py)

```python
import asyncio
from pathlib import Path
from lazyplex import application, apply_plugins
from lazyplex.plugins import progress_bar

# Create some test files
def create_test_files():
    test_dir = Path("./test_data")
    test_dir.mkdir(exist_ok=True)

    files = []
    for i in range(3):
        file_path = test_dir / f"test_{i}.txt"
        with open(file_path, 'w') as f:
            f.write(f"This is test file {i} with some content.\n" * (i + 1))
        files.append(file_path)

    return files

@application
async def process_files():
    files = create_test_files()

    async with apply_plugins(progress_bar(len(files))):
        return files  # Process all files in parallel

@process_files.action
async def process_file(file_path):
    # Simulate file processing
    await asyncio.sleep(0.1)

    with open(file_path, 'r') as f:
        content = f.read()

    # Process content (e.g., word count)
    word_count = len(content.split())

    result = {
        'file': file_path.name,
        'size': file_path.stat().st_size,
        'words': word_count
    }
    print(f"Processed {file_path.name}: {word_count} words")
    return result

if __name__ == "__main__":
    try:
        results = process_files.run_until_complete()
        print(f"Results: {results}")

        # Cleanup
        import shutil
        if Path("./test_data").exists():
            shutil.rmtree("./test_data")
    except Exception as e:
        print(f"Error: {e}")
```

### Web Scraping Example

```python
import asyncio
import aiohttp
from lazyplex import application, apply_plugins
from lazyplex.plugins import progress_bar

@application
async def fetch_urls():
    urls = [
        "https://api.github.com/users/octocat",
        "https://api.github.com/users/defunkt",
        "https://api.github.com/users/pjhyett"
    ]

    async with apply_plugins(progress_bar(len(urls))):
        return urls  # Parallel processing

@fetch_urls.action
async def fetch_user_data(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()
            return {
                'login': data['login'],
                'name': data.get('name', 'N/A'),
                'public_repos': data['public_repos']
            }

# Usage
if __name__ == '__main__':
    results = fetch_urls.run_until_complete()
    for user in results:
        print(f"{user['name']} ({user['login']}): {user['public_repos']} repos")
```

## Project Structure

```
lazyplex/
├── src/lazyplex/
│   ├── __init__.py              # Main exports
│   ├── run.py                   # CLI runner
│   ├── core/
│   │   ├── __init__.py          # Core exports
│   │   ├── actions.py           # Action classes
│   │   ├── application.py       # Application class
│   │   ├── constants.py         # Constants
│   │   ├── context.py           # Context management
│   │   ├── errors.py            # Custom exceptions
│   │   ├── helpers.py           # Utility functions
│   │   └── plugin.py            # Plugin base class
│   ├── operators/
│   │   ├── __init__.py
│   │   ├── dist.py              # Distribution operators
│   │   └── random.py            # Random operators
│   └── plugins/
│       ├── __init__.py
│       └── progress_bar.py      # Progress bar plugin
├── examples/                    # Example applications
└── pyproject.toml               # Project configuration
```

## Dependencies

- **Python 3.11+** (required)
- **tqdm** - Progress bar functionality
- **asyncio** - Asynchronous processing (built-in)

## Error Handling

Applications can be configured to handle exceptions:

```python
@application(return_exceptions=True)
async def error_tolerant():
    return [1, 2, "invalid", 4]

@error_tolerant.action
async def might_fail(item):
    return int(item) * 2  # Will raise exception for "invalid"

# Results will include the exception object for "invalid"
results = error_tolerant.run_until_complete()
```

## Context Management

The framework provides sophisticated context handling with two-tier context system:

- **Application-level context**: Common data shared across all items
- **Action-specific context**: Unique data per item during processing

### Context Management Example (from examples/context.py)

```python
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
    results = context_example.run_until_complete()
    print(f"Results: {results}")
```

## Argument Processing

Applications support argument processing with decorators:

### Argument Processing Example (from examples/argument_processing.py)

```python
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
    # Test with default multiplier
    results1 = with_args.run_until_complete()
    print(f"Results: {results1[:5]}...")

    # Test with custom multiplier
    results2 = with_args.run_until_complete(multiplier=3)
    print(f"Results: {results2[:5]}...")
```

## Command Line Usage

Run applications from the command line:

```bash
# Basic usage
python -m lazyplex example.app

# With the run module
python -m lazyplex.run example.app
```

## Version Information

Current version: 0.0.3 (as specified in pyproject.toml)

## Processing Logic Summary

The framework determines processing mode based on:

1. **Parallel Processing**: When `protected_items=False` (default) and you return an `Iterable` or `AsyncIterable`
2. **Sequential Processing**: When you yield individual items in a loop
3. **Single Item Processing**: When `protected_items=True` or when no iterable is detected

**Key Point**: Returning `iter([1,2,3])` still results in parallel processing because iterators are iterable. For true sequential processing, use `yield` in a loop.

## LLM Integration Notes

This framework is designed to be:
- **Composable**: Easy to combine with other async libraries
- **Extensible**: Plugin system allows custom functionality
- **Predictable**: Clear separation between data definition and processing logic
- **Debuggable**: Built-in context management and error handling
- **Scalable**: Supports both parallel and sequential processing patterns

The decorator-based API makes it particularly suitable for code generation and automated refactoring tasks. The distinction between parallel and sequential processing is crucial for performance optimization in different use cases.

## Best Practices

1. **Use parallel processing** for I/O-bound tasks that can run concurrently
2. **Use sequential processing** when order matters or when you need to control resource usage
3. **Use plugins** to add cross-cutting concerns like logging, metrics, or progress tracking
4. **Use context management** to share state between actions
5. **Use error handling** to gracefully handle failures in batch processing
6. **Use protected_items=True** when you need to process collections as single units