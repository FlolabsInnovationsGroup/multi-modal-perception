#!/usr/bin/env python3
"""
Merge all task annotations into unified_train.jsonl and unified_val.jsonl.
Paths in each record are prefixed with task name so loaders can resolve them.
"""
from pathlib import Path
import json
import random

DATASET_ROOT = Path(__file__).resolve().parent.parent
TASKS_DIR = DATASET_ROOT / "tasks"
UNIFIED_TRAIN = DATASET_ROOT / "unified_train.jsonl"
UNIFIED_VAL = DATASET_ROOT / "unified_val.jsonl"

# Fraction of each task to use for validation
VAL_RATIO = 0.1
RANDOM_SEED = 42


def load_task_annotations(task_name: str) -> list[dict]:
    """Load annotations.jsonl for a task; add task and resolve path key."""
    ann_path = TASKS_DIR / task_name / "annotations.jsonl"
    if not ann_path.exists():
        return []
    records = []
    with open(ann_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            rec["task"] = task_name
            # Path key is either image_path or context_path
            if "image_path" in rec:
                rec["path_key"] = "image_path"
            elif "context_path" in rec:
                rec["path_key"] = "context_path"
            else:
                rec["path_key"] = None
            records.append(rec)
    return records


def main():
    random.seed(RANDOM_SEED)
    all_records = []

    for task_dir in TASKS_DIR.iterdir():
        if not task_dir.is_dir():
            continue
        task_name = task_dir.name
        records = load_task_annotations(task_name)
        for r in records:
            # Store path relative to task dir (as in original annotations)
            all_records.append(r)

    random.shuffle(all_records)
    n = len(all_records)
    n_val = max(1, int(n * VAL_RATIO))
    n_train = n - n_val
    train_records = all_records[:n_train]
    val_records = all_records[n_train:]

    def write_jsonl(path: Path, records: list[dict]) -> None:
        with open(path, "w") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    write_jsonl(UNIFIED_TRAIN, train_records)
    write_jsonl(UNIFIED_VAL, val_records)
    print(f"Wrote {len(train_records)} train, {len(val_records)} val to {DATASET_ROOT}")


if __name__ == "__main__":
    main()
