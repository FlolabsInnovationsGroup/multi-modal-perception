import json
import re
from pathlib import Path
from typing import Any, Dict, List, Set, Optional


def normalize_prediction_items(predictions: Any) -> List[Dict[str, Any]]:
    """
    Normalize prediction JSON into a list of prediction items.

    Supported formats:
      1. [
           {"id": "ingredient_000001", ...}
         ]

      2. {
           "summary": {...},
           "results": [
             {"id": "ingredient_000001", ...}
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

# =========================
# JSON IO
# =========================
def load_json(json_path: str) -> Any:
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: Any, json_path: str) -> None:
    json_path = Path(json_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# =========================
# Ingredient normalization
# =========================
def normalize_ingredient_name(name: Any) -> Optional[str]:
    """
    Normalize one ingredient name.

    Examples:
        "Green Onion" -> "green onion"
        " green_onion " -> "green onion"
    """
    if not isinstance(name, str):
        return None

    name = name.strip().lower()
    name = name.replace("_", " ")
    name = re.sub(r"\s+", " ", name)

    if not name:
        return None

    return name


def normalize_ingredient_list(value: Any) -> Set[str]:
    """
    Convert model or metadata ingredient field into a normalized set.

    Expected input:
        ["rice", "egg", "green onion"]

    Also handles unexpected string input:
        "rice, egg, green onion"
    """
    ingredients = set()

    if value is None:
        return ingredients

    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, str):
        # fallback for cases like "rice, egg, carrot"
        raw_items = re.split(r"[,;，；]", value)
    else:
        return ingredients

    for item in raw_items:
        normalized = normalize_ingredient_name(item)
        if normalized is not None:
            ingredients.add(normalized)

    return ingredients


# =========================
# Metric calculation
# =========================
def compute_set_metrics(
    predicted_set: Set[str],
    ground_truth_set: Set[str],
) -> Dict[str, Any]:
    """
    Compute Precision, Recall, F1, Hallucination Rate for one prediction set.
    """
    true_positive_items = sorted(predicted_set & ground_truth_set)
    false_positive_items = sorted(predicted_set - ground_truth_set)
    false_negative_items = sorted(ground_truth_set - predicted_set)

    tp = len(true_positive_items)
    fp = len(false_positive_items)
    fn = len(false_negative_items)

    if tp + fp > 0:
        precision = tp / (tp + fp)
        hallucination_rate = fp / (tp + fp)
    else:
        precision = 0.0
        hallucination_rate = 0.0

    if tp + fn > 0:
        recall = tp / (tp + fn)
    else:
        recall = 0.0

    if precision + recall > 0:
        f1_score = 2 * precision * recall / (precision + recall)
    else:
        f1_score = 0.0

    return {
        "precision": precision,
        "recall": recall,
        "f1_score": f1_score,
        "hallucination_rate": hallucination_rate,
        "counts": {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "num_predicted": len(predicted_set),
            "num_ground_truth": len(ground_truth_set),
        },
        "items": {
            "true_positive": true_positive_items,
            "false_positive": false_positive_items,
            "false_negative": false_negative_items,
        },
    }


def compute_micro_metrics(total_tp: int, total_fp: int, total_fn: int) -> Dict[str, float]:
    """
    Compute micro-averaged metrics from accumulated TP, FP, FN.
    """
    if total_tp + total_fp > 0:
        precision = total_tp / (total_tp + total_fp)
        hallucination_rate = total_fp / (total_tp + total_fp)
    else:
        precision = 0.0
        hallucination_rate = 0.0

    if total_tp + total_fn > 0:
        recall = total_tp / (total_tp + total_fn)
    else:
        recall = 0.0

    if precision + recall > 0:
        f1_score = 2 * precision * recall / (precision + recall)
    else:
        f1_score = 0.0

    return {
        "precision": precision,
        "recall": recall,
        "f1_score": f1_score,
        "hallucination_rate": hallucination_rate,
    }


def average_metric(
    per_sample_results: List[Dict[str, Any]],
    scope_name: str,
    metric_name: str,
) -> float:
    """
    Compute macro average of one metric over valid samples.
    """
    values = []

    for item in per_sample_results:
        if item.get("status") != "valid":
            continue

        metric_value = item["metrics"][scope_name][metric_name]
        values.append(metric_value)

    if not values:
        return 0.0

    return sum(values) / len(values)


# =========================
# Main evaluation function
# =========================
def evaluate_ingredient_estimation(
    prediction_json_path: str,
    metadata_json_path: str,
    output_json_path: str,
    gt_key: str = "ingredients",
    pred_keys: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Offline evaluation for ingredient estimation.

    Model prediction format:
        [
          {
            "id": "ingredient_000001",
            "visible_ingredients": [],
            "likely_ingredients": [],
            "uncertain_or_hidden": []
          }
        ]

    Metadata format:
        [
          {
            "id": "ingredient_000001",
            "image_path": "./images/ingredient_000001.jpg",
            "ingredients": ["rice", "egg"],
            "sample_type": "boundary",
            "food_name": "salad"
          }
        ]

    Evaluation scopes:
        1. all_ingredients:
            union of visible_ingredients, likely_ingredients, uncertain_or_hidden

        2. visible_ingredients

        3. likely_ingredients

        4. uncertain_or_hidden
    """
    if pred_keys is None:
        pred_keys = [
            "visible_ingredients",
            "likely_ingredients",
            "uncertain_or_hidden",
        ]

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

    evaluation_scopes = ["all_ingredients"] + pred_keys

    per_sample_results: List[Dict[str, Any]] = []

    missing_prediction_ids = []
    invalid_ground_truth_ids = []

    # For micro-average
    total_counts = {
        scope: {
            "tp": 0,
            "fp": 0,
            "fn": 0,
            "num_predicted": 0,
            "num_ground_truth": 0,
        }
        for scope in evaluation_scopes
    }

    for sample_id, meta_item in metadata_map.items():
        ground_truth_set = normalize_ingredient_list(meta_item.get(gt_key))

        if not ground_truth_set:
            invalid_ground_truth_ids.append(sample_id)

            per_sample_results.append(
                {
                    "id": sample_id,
                    "status": "invalid_ground_truth",
                    "image_path": meta_item.get("image_path"),
                    "sample_type": meta_item.get("sample_type"),
                    "food_name": meta_item.get("food_name"),
                    "ground_truth_ingredients": sorted(ground_truth_set),
                    "prediction": None,
                    "metrics": None,
                }
            )
            continue

        pred_item = pred_map.get(sample_id)

        if pred_item is None:
            missing_prediction_ids.append(sample_id)

            per_sample_results.append(
                {
                    "id": sample_id,
                    "status": "missing_prediction",
                    "image_path": meta_item.get("image_path"),
                    "sample_type": meta_item.get("sample_type"),
                    "food_name": meta_item.get("food_name"),
                    "ground_truth_ingredients": sorted(ground_truth_set),
                    "prediction": None,
                    "metrics": None,
                }
            )
            continue

        predicted_sets = {}

        for key in pred_keys:
            predicted_sets[key] = normalize_ingredient_list(pred_item.get(key))

        all_predicted_set = set()
        for key in pred_keys:
            all_predicted_set.update(predicted_sets[key])

        predicted_sets["all_ingredients"] = all_predicted_set

        sample_metrics = {}

        for scope in evaluation_scopes:
            metrics = compute_set_metrics(
                predicted_set=predicted_sets[scope],
                ground_truth_set=ground_truth_set,
            )

            sample_metrics[scope] = metrics

            counts = metrics["counts"]

            total_counts[scope]["tp"] += counts["tp"]
            total_counts[scope]["fp"] += counts["fp"]
            total_counts[scope]["fn"] += counts["fn"]
            total_counts[scope]["num_predicted"] += counts["num_predicted"]
            total_counts[scope]["num_ground_truth"] += counts["num_ground_truth"]

        per_sample_results.append(
            {
                "id": sample_id,
                "status": "valid",
                "image_path": meta_item.get("image_path"),
                "sample_type": meta_item.get("sample_type"),
                "food_name": meta_item.get("food_name"),
                "ground_truth_ingredients": sorted(ground_truth_set),
                "prediction": {
                    "all_ingredients": sorted(predicted_sets["all_ingredients"]),
                    "visible_ingredients": sorted(predicted_sets["visible_ingredients"]),
                    "likely_ingredients": sorted(predicted_sets["likely_ingredients"]),
                    "uncertain_or_hidden": sorted(predicted_sets["uncertain_or_hidden"]),
                },
                "metrics": sample_metrics,
            }
        )

    summary_by_scope = {}

    for scope in evaluation_scopes:
        counts = total_counts[scope]

        micro_metrics = compute_micro_metrics(
            total_tp=counts["tp"],
            total_fp=counts["fp"],
            total_fn=counts["fn"],
        )

        macro_metrics = {
            "precision": average_metric(per_sample_results, scope, "precision"),
            "recall": average_metric(per_sample_results, scope, "recall"),
            "f1_score": average_metric(per_sample_results, scope, "f1_score"),
            "hallucination_rate": average_metric(
                per_sample_results,
                scope,
                "hallucination_rate",
            ),
        }

        summary_by_scope[scope] = {
            "micro": micro_metrics,
            "macro": macro_metrics,
            "counts": counts,
        }

    result = {
        "summary": {
            "num_metadata_samples": len(metadata_map),
            "num_prediction_samples": len(pred_map),
            "num_valid_samples": len(
                [item for item in per_sample_results if item["status"] == "valid"]
            ),
            "num_missing_predictions": len(missing_prediction_ids),
            "num_invalid_ground_truth": len(invalid_ground_truth_ids),
            "metrics_by_scope": summary_by_scope,
        },
        "details": per_sample_results,
        "missing_prediction_ids": missing_prediction_ids,
        "invalid_ground_truth_ids": invalid_ground_truth_ids,
    }

    save_json(result, output_json_path)

    print(f"Evaluation result saved to: {output_json_path}")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))

    return result


# =========================
# Main
# =========================
if __name__ == "__main__":
    prediction_json_path = "./outputs/ingredients_results_with_metrics.json"
    metadata_json_path = "./data/ingredient/ingredient_metadata.json"
    output_json_path = "./outputs/ingredient_eval_results.json"

    evaluate_ingredient_estimation(
        prediction_json_path=prediction_json_path,
        metadata_json_path=metadata_json_path,
        output_json_path=output_json_path,
    )