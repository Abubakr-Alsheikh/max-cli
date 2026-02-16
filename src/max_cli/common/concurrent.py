from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, TypeVar

from rich.progress import Progress, TaskID

T = TypeVar("T")
R = TypeVar("R")


def process_batch_parallel(
    items: List[T],
    processor: Callable[[T], R],
    max_workers: int = 4,
    progress: Optional[Progress] = None,
    task_id: Optional[TaskID] = None,
) -> List[Dict[str, Any]]:
    """Process items in parallel with optional progress tracking.

    Args:
        items: List of items to process
        processor: Function to apply to each item
        max_workers: Maximum number of parallel workers
        progress: Optional Rich Progress instance
        task_id: Optional Rich TaskID for progress tracking

    Returns:
        List of results, including errors for failed items
    """
    results: List[Dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(processor, item): item for item in items}

        for future in as_completed(futures):
            item = futures[future]
            try:
                result = future.result()
                if isinstance(result, dict):
                    results.append(result)
                else:
                    results.append({"result": result, "item": item})
            except Exception as e:
                results.append({"error": str(e), "item": item, "success": False})

            if progress is not None and task_id is not None:
                progress.advance(task_id)

    return results


def process_batch_sequential(
    items: List[T],
    processor: Callable[[T], R],
    progress: Optional[Progress] = None,
    task_id: Optional[TaskID] = None,
) -> List[Dict[str, Any]]:
    """Process items sequentially with optional progress tracking.

    Args:
        items: List of items to process
        processor: Function to apply to each item
        progress: Optional Rich Progress instance
        task_id: Optional Rich TaskID for progress tracking

    Returns:
        List of results, including errors for failed items
    """
    results: List[Dict[str, Any]] = []

    for item in items:
        try:
            result = processor(item)
            if isinstance(result, dict):
                results.append(result)
            else:
                results.append({"result": result, "item": item})
        except Exception as e:
            results.append({"error": str(e), "item": item, "success": False})

        if progress is not None and task_id is not None:
            progress.advance(task_id)

    return results
