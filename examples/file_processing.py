#!/usr/bin/env python3
"""Test a simplified file processing example from README"""

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
    print("Testing file processing example...")
    try:
        results = process_files.run_until_complete()
        print(f"Results: {results}")

        # Cleanup
        import shutil
        if Path("./test_data").exists():
            shutil.rmtree("./test_data")

    except Exception as e:
        print(f"Error: {e}")
    print("File processing example completed!")