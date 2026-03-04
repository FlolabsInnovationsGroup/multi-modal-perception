#!/usr/bin/env python3
"""
Example loader for caipo_multimodal_dataset.
Reads unified_train.jsonl / unified_val.jsonl and resolves paths to task dirs.
Can be adapted for HuggingFace datasets or custom training loops.
"""
from pathlib import Path
import json

DATASET_ROOT = Path(__file__).resolve().parent.parent
UNIFIED_TRAIN = DATASET_ROOT / "unified_train.jsonl"
UNIFIED_VAL = DATASET_ROOT / "unified_val.jsonl"
TASKS_DIR = DATASET_ROOT / "tasks"


def iter_unified(split: str = "train"):
    """Yield records from unified_train.jsonl or unified_val.jsonl."""
    path = UNIFIED_TRAIN if split == "train" else UNIFIED_VAL
    if not path.exists():
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def resolve_path(record: dict) -> Path | None:
    """
    Resolve image_path or context_path to an absolute path.
    Path in record is relative to the task dir (e.g. images/pizza_001.jpg).
    """
    task = record.get("task")
    if not task:
        return None
    task_dir = TASKS_DIR / task
    if "image_path" in record:
        return task_dir / record["image_path"]
    if "context_path" in record:
        return task_dir / record["context_path"]
    return None


def load_dialogue(path: Path) -> dict | None:
    """Load a dialogue JSON (for conversation_identity task)."""
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def example_usage():
    """Print first few train records and resolved paths."""
    print("Dataset root:", DATASET_ROOT)
    print("Train samples:")
    for i, rec in enumerate(iter_unified("train")):
        if i >= 3:
            break
        resolved = resolve_path(rec)
        print(f"  task={rec.get('task')} instruction={rec.get('instruction')[:50]}... path={resolved}")
    print("Val samples:")
    for i, rec in enumerate(iter_unified("val")):
        if i >= 2:
            break
        resolved = resolve_path(rec)
        print(f"  task={rec.get('task')} path={resolved}")


if __name__ == "__main__":
    example_usage()
