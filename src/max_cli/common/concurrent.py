import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, TypeVar

from max_cli.common.events import (
    BatchProgressEvent,
    CompleteEvent,
    EventEmitter,
    FileCompleteEvent,
    FileErrorEvent,
    FileStartEvent,
)

T = TypeVar("T")
R = TypeVar("R")


def process_batch_parallel(
    items: List[T],
    processor: Callable[[T], R],
    max_workers: int = 4,
    emitter: Optional[EventEmitter] = None,
    action: str = "Processing",
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    total = len(items)
    processed_count = 0
    count_lock = threading.Lock()

    def _emit_progress():
        if emitter:
            with count_lock:
                current = processed_count
            emitter.emit(
                BatchProgressEvent(
                    current=current,
                    total=total,
                    percentage=(current / total * 100) if total > 0 else 0,
                    description=f"{action}...",
                )
            )

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(processor, item): item for item in items}

        for future in as_completed(futures):
            item = futures[future]
            item_name = str(item) if hasattr(item, "__str__") else repr(item)

            if emitter:
                emitter.emit(FileStartEvent(file=item_name, action=action))

            try:
                result = future.result()
                if isinstance(result, dict):
                    results.append(result)
                else:
                    results.append({"result": result, "item": item})

                if emitter:
                    event_result = (
                        result
                        if isinstance(result, dict)
                        else {"result": result, "item": item}
                    )
                    emitter.emit(FileCompleteEvent(file=item_name, result=event_result))
            except Exception as e:
                error_msg = str(e)
                results.append({"error": error_msg, "item": item, "success": False})

                if emitter:
                    emitter.emit(FileErrorEvent(file=item_name, error=error_msg))

            with count_lock:
                processed_count += 1
            _emit_progress()

    if emitter:
        emitter.emit(
            CompleteEvent(
                summary={
                    "total": total,
                    "successful": sum(1 for r in results if "error" not in r),
                    "failed": sum(1 for r in results if "error" in r),
                }
            )
        )

    return results


def process_batch_sequential(
    items: List[T],
    processor: Callable[[T], R],
    emitter: Optional[EventEmitter] = None,
    action: str = "Processing",
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    total = len(items)

    for i, item in enumerate(items):
        item_name = str(item) if hasattr(item, "__str__") else repr(item)

        if emitter:
            emitter.emit(FileStartEvent(file=item_name, action=action))

        try:
            result = processor(item)
            if isinstance(result, dict):
                results.append(result)
            else:
                results.append({"result": result, "item": item})

            if emitter:
                event_result = (
                    result
                    if isinstance(result, dict)
                    else {"result": result, "item": item}
                )
                emitter.emit(FileCompleteEvent(file=item_name, result=event_result))
        except Exception as e:
            error_msg = str(e)
            results.append({"error": error_msg, "item": item, "success": False})

            if emitter:
                emitter.emit(FileErrorEvent(file=item_name, error=error_msg))

        if emitter:
            emitter.emit(
                BatchProgressEvent(
                    current=i + 1,
                    total=total,
                    percentage=((i + 1) / total * 100) if total > 0 else 0,
                    description=f"{action}...",
                )
            )

    if emitter:
        emitter.emit(
            CompleteEvent(
                summary={
                    "total": total,
                    "successful": sum(1 for r in results if "error" not in r),
                    "failed": sum(1 for r in results if "error" in r),
                }
            )
        )

    return results
