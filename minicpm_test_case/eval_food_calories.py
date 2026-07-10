import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def normalize_prediction_items(predictions: Any) -> List[Dict[str, Any]]:
    """
    Normalize prediction JSON into a list of prediction items.

    Supported formats:
    1. [
         {"id": "calorie_000001", "calorie_kcal": 450}
       ]

    2. {
         "summary": {...},
         "results": [
           {"id": "calorie_000001", "calorie_kcal": 450, ...}
         ]
       }
    """
    if isinstance(predictions, list):
        return predictions

    if isinstance(predictions, dict):
        if "results" in predictions and isinstance(predictions["results"], list):
            return predictions["results"]

    raise ValueError(
        "Unsupported prediction JSON format. "
        "Expected a list or a dict with a 'results' list."
    )

def load_json(json_path: str) -> Any:
    """
    Load JSON file.
    """
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: Any, json_path: str) -> None:
    """
    Save data to JSON file.
    """
    json_path = Path(json_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def to_float(value: Any) -> Optional[float]:
    """
    Convert value to float if possible.
    Return None if conversion fails.
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def evaluate_calorie_estimation(
    prediction_json_path: str,
    metadata_json_path: str,
    output_json_path: str,
    pred_key: str = "calorie_kcal",
    gt_key: str = "calorie_kcal",
) -> Dict[str, Any]:
    """
    Offline evaluation for calorie estimation.

    Metrics:
        MAE:
            Mean Absolute Error, measured in kcal.

        MAPE:
            Mean Absolute Percentage Error, measured as a percentage.

    Args:
        prediction_json_path:
            Path to model prediction JSON file.
            Example:
            [
              {
                "id": "calorie_000001",
                "calorie_kcal": 520.0
              }
            ]

        metadata_json_path:
            Path to metadata JSON file.
            Example:
            [
              {
                "id": "calorie_000001",
                "image_path": "./images/calorie_000001.jpg",
                "calorie_kcal": 523.5,
                "sample_type": "normal"
              }
            ]

        output_json_path:
            Path to save evaluation result JSON.

        pred_key:
            Prediction field name. Default is "calorie_kcal".

        gt_key:
            Ground-truth field name. Default is "calorie_kcal".

    Returns:
        Evaluation result dictionary.
    """
    predictions_raw = load_json(prediction_json_path)
    metadata = load_json(metadata_json_path)

    predictions = normalize_prediction_items(predictions_raw)

    pred_map = {
        item["id"]: item
        for item in predictions
        if isinstance(item, dict) and "id" in item
    }

    metadata_map = {
        item["id"]: item
        for item in metadata
        if isinstance(item, dict) and "id" in item
    }

    per_sample_results: List[Dict[str, Any]] = []

    abs_errors = []
    ape_values = []

    missing_prediction_ids = []
    invalid_prediction_ids = []
    invalid_ground_truth_ids = []

    for sample_id, meta_item in metadata_map.items():
        pred_item = pred_map.get(sample_id)

        gt_value = to_float(meta_item.get(gt_key))

        if gt_value is None:
            invalid_ground_truth_ids.append(sample_id)
            per_sample_results.append(
                {
                    "id": sample_id,
                    "status": "invalid_ground_truth",
                    "ground_truth": meta_item.get(gt_key),
                    "prediction": None,
                    "sample_type": meta_item.get("sample_type"),
                    "image_path": meta_item.get("image_path"),
                }
            )
            continue

        if pred_item is None:
            missing_prediction_ids.append(sample_id)
            per_sample_results.append(
                {
                    "id": sample_id,
                    "status": "missing_prediction",
                    "ground_truth": gt_value,
                    "prediction": None,
                    "sample_type": meta_item.get("sample_type"),
                    "image_path": meta_item.get("image_path"),
                }
            )
            continue

        pred_value = to_float(pred_item.get(pred_key))

        if pred_value is None:
            invalid_prediction_ids.append(sample_id)
            per_sample_results.append(
                {
                    "id": sample_id,
                    "status": "invalid_prediction",
                    "ground_truth": gt_value,
                    "prediction": pred_item.get(pred_key),
                    "sample_type": meta_item.get("sample_type"),
                    "image_path": meta_item.get("image_path"),
                    "raw_prediction": pred_item,
                }
            )
            continue

        abs_error = abs(pred_value - gt_value)

        abs_errors.append(abs_error)

        if gt_value != 0:
            ape_percent = abs_error / abs(gt_value) * 100
            ape_values.append(ape_percent)
        else:
            ape_percent = None

        per_sample_results.append(
            {
                "id": sample_id,
                "status": "valid",
                "prediction": pred_value,
                "ground_truth": gt_value,
                "absolute_error_kcal": abs_error,
                "absolute_percentage_error_percent": ape_percent,
                "sample_type": meta_item.get("sample_type"),
                "image_path": meta_item.get("image_path"),
            }
        )

    mae = sum(abs_errors) / len(abs_errors) if abs_errors else None
    mape = sum(ape_values) / len(ape_values) if ape_values else None

    result = {
        "summary": {
            "num_metadata_samples": len(metadata_map),
            "num_prediction_samples": len(pred_map),
            "num_valid_samples": len(abs_errors),
            "num_missing_predictions": len(missing_prediction_ids),
            "num_invalid_predictions": len(invalid_prediction_ids),
            "num_invalid_ground_truth": len(invalid_ground_truth_ids),
            "num_mape_excluded_due_to_zero_ground_truth": len(abs_errors) - len(ape_values),
            "MAE_kcal": mae,
            "MAPE_percent": mape,
        },
        "details": per_sample_results,
        "missing_prediction_ids": missing_prediction_ids,
        "invalid_prediction_ids": invalid_prediction_ids,
        "invalid_ground_truth_ids": invalid_ground_truth_ids,
    }

    save_json(result, output_json_path)

    print(f"Evaluation result saved to: {output_json_path}")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))

    return result


if __name__ == "__main__":
    prediction_json_path = "./outputs/calorie_results_with_metrics_MiniCPM-V-4.6-Instruct.json"
    metadata_json_path = "./data/food_calories/calorie_metadata.json"
    output_json_path = "./outputs/calorie_eval_results.json"

    evaluate_calorie_estimation(
        prediction_json_path=prediction_json_path,
        metadata_json_path=metadata_json_path,
        output_json_path=output_json_path,
        pred_key="calorie_kcal",
        gt_key="calorie_kcal",
    )