import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from openai import OpenAI


# =========================
# MiniCPM API
# =========================
minicpm_api_key = os.getenv(
    "MINICPM_API_KEY",
    "lis_sk_298cf78155f231c7_DkrDcNLHnK8dJRnfFrJCd4JGDbBLMkHrC3T-wLpvC9zy0BPemsyFuQ",
)

client = OpenAI(
    api_key=minicpm_api_key,
    base_url="https://api.modelbest.co/v1",
)

MODEL_NAME = "MiniCPM-V-4.6-Instruct"
MAX_API_RETRIES = 3
RETRY_DELAY_SECONDS = 2


# =========================
# Prediction normalization
# =========================
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
    json_path_obj = Path(json_path)
    json_path_obj.parent.mkdir(parents=True, exist_ok=True)

    with open(json_path_obj, "w", encoding="utf-8") as f:
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
    Convert a model or metadata ingredient field into a normalized set.

    Expected input:
        ["rice", "egg", "green onion"]

    Also handles string input:
        "rice, egg, green onion"
    """
    ingredients: Set[str] = set()

    if value is None:
        return ingredients

    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, str):
        raw_items = re.split(r"[,;，；]", value)
    else:
        return ingredients

    for item in raw_items:
        normalized = normalize_ingredient_name(item)
        if normalized is not None:
            ingredients.add(normalized)

    return ingredients


# =========================
# MiniCPM synonym replacement
# =========================
SYNONYM_SYSTEM_PROMPT = """
你是严格的食材同义词判断器。

你的唯一任务是：对每一个 output 食材，判断 metadata 食材列表中是否存在与它表示同一种实际食材的名称。

规则：
1. 可以视为同一种食材的情况包括：同义词、常见别名、中英文等价名称、单复数变化、词形变化，以及不改变食材本体的常见描述差异。
2. 完全相同的名称当然属于同一种食材。
3. 只有确实表示同一种实际食材时，才返回对应的 metadata 下标。
4. 如果不存在同义词或等价名称，对应位置必须返回 JSON 空值 null。
5. 不要因为两种食材经常共同出现、可以互相替代、属于同一大类，就判断为同一种食材。
6. 宽泛类别与具体食材不等价，例如 vegetable 与 carrot 不等价。
7. 原料与制品不等价，例如 tomato 与 tomato sauce、olive 与 olive oil、milk 与 cheese 不等价。
8. 多个 output 别名可以指向同一个 metadata 食材。
9. 只返回一个 JSON 对象，且只能包含 metadata_indices 字段。
10. metadata_indices 必须是一个数组，长度必须与 output_ingredients 完全相同。
11. 数组第 i 个值对应 output_ingredients 第 i 个词；匹配时填 metadata 的整数下标，不匹配时填 null。
12. null 必须是不带引号的 JSON 空值。数组中不要写 metadata_index 键，不要返回食材文本。
13. 不要输出 Markdown、代码块、解释、注释或额外文本。

正确格式示例：
{"metadata_indices": [null, 4, null, 1]}
""".strip()


def build_synonym_prompt(
    sample_id: str,
    output_ingredients: List[str],
    metadata_ingredients: List[str],
) -> str:
    """
    Build one MiniCPM request for one dish.

    The array position is the output index. The array value is the matched
    metadata index, or null when no equivalent metadata ingredient exists.
    """
    input_data = {
        "id": sample_id,
        "output_ingredients": output_ingredients,
        "metadata_ingredients": metadata_ingredients,
    }

    return (
        "逐一判断 output_ingredients 中的每个食材是否与 metadata_ingredients 中某个食材表示同一种实际食材。\n"
        "只返回如下结构：{\"metadata_indices\": [...]}。\n"
        "metadata_indices 的长度必须等于 output_ingredients 的长度。\n"
        "第 i 个位置匹配时填写 metadata_ingredients 的整数下标；不匹配时填写 null。\n"
        "不要返回 output_index，不要在数组元素中写 metadata_index 键，不要返回任何食材文本。\n\n"
        "输入：\n"
        f"{json.dumps(input_data, ensure_ascii=False, indent=2)}"
    )


def _find_matching_square_bracket(text: str, opening_index: int) -> Optional[int]:
    """Find the matching closing square bracket while respecting JSON strings."""
    depth = 0
    in_string = False
    escaped = False

    for index in range(opening_index, len(text)):
        character = text[index]

        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue

        if character == '"':
            in_string = True
        elif character == "[":
            depth += 1
        elif character == "]":
            depth -= 1
            if depth == 0:
                return index

    return None


def _split_top_level_array_items(array_body: str) -> List[str]:
    """Split a possibly malformed JSON array without splitting nested objects."""
    items: List[str] = []
    start = 0
    brace_depth = 0
    bracket_depth = 0
    in_string = False
    escaped = False

    for index, character in enumerate(array_body):
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue

        if character == '"':
            in_string = True
        elif character == "{":
            brace_depth += 1
        elif character == "}":
            brace_depth = max(0, brace_depth - 1)
        elif character == "[":
            bracket_depth += 1
        elif character == "]":
            bracket_depth = max(0, bracket_depth - 1)
        elif character == "," and brace_depth == 0 and bracket_depth == 0:
            items.append(array_body[start:index].strip())
            start = index + 1

    final_item = array_body[start:].strip()
    if final_item or array_body.strip():
        items.append(final_item)

    return items


def _parse_loose_index_item(item: str) -> Any:
    """
    Parse one index item from either the new compact format or common malformed
    variants produced by the model.
    """
    stripped = item.strip()

    if stripped.lower() in {"null", '"null"', "none", '"none"', ""}:
        return None

    if re.fullmatch(r"-?\d+", stripped):
        return int(stripped)

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    metadata_match = re.search(
        r'["\']?metadata_index["\']?\s*:\s*(null|"null"|none|"none"|-?\d+)',
        stripped,
        flags=re.IGNORECASE,
    )
    if metadata_match:
        raw_value = metadata_match.group(1)
        if raw_value.lower().strip('"') in {"null", "none"}:
            return None
        return int(raw_value)

    return None


def extract_synonym_response(response_content: str) -> Dict[str, Any]:
    """
    Parse the normal JSON response first. If the model emits a common malformed
    array, recover the array positions instead of aborting the whole evaluation.
    """
    content = response_content.strip()

    # Normal valid JSON path.
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Recover a valid JSON object embedded in surrounding text.
    decoder = json.JSONDecoder()
    for index, character in enumerate(content):
        if character != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(content[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed

    # Recover the compact array, and also the old "decisions" key, from common
    # malformed outputs such as:
    # {"decisions": [null, "null", "metadata_index": 4, null]}
    key_match = re.search(
        r'["\']?(metadata_indices|decisions)["\']?\s*:\s*\[',
        content,
        flags=re.IGNORECASE,
    )
    if key_match:
        opening_index = content.find("[", key_match.start())
        closing_index = _find_matching_square_bracket(content, opening_index)
        if closing_index is not None:
            array_body = content[opening_index + 1 : closing_index]
            recovered_items = [
                _parse_loose_index_item(item)
                for item in _split_top_level_array_items(array_body)
            ]
            return {"metadata_indices": recovered_items}

    raise ValueError(
        "MiniCPM response does not contain a recoverable synonym index array. "
        f"Raw response: {response_content}"
    )


def parse_synonym_decisions(
    response_json: Dict[str, Any],
    num_output_ingredients: int,
    num_metadata_ingredients: int,
) -> Dict[int, Optional[int]]:
    """
    Parse both the new compact format and the old object-list format.

    New preferred format:
        {"metadata_indices": [null, 4, null]}

    Any missing, malformed, or out-of-range item is treated as no replacement,
    so the original output word is retained.
    """
    decisions_by_output_index: Dict[int, Optional[int]] = {}

    metadata_indices = response_json.get("metadata_indices")
    if isinstance(metadata_indices, list):
        for output_index in range(num_output_ingredients):
            if output_index >= len(metadata_indices):
                decisions_by_output_index[output_index] = None
                continue

            item = metadata_indices[output_index]

            # Tolerate quoted null and legacy object elements.
            if isinstance(item, str) and item.strip().lower() in {"null", "none", ""}:
                item = None

            if isinstance(item, dict):
                item = item.get("metadata_index")

            if item is None:
                decisions_by_output_index[output_index] = None
                continue

            if isinstance(item, bool) or not isinstance(item, int):
                decisions_by_output_index[output_index] = None
                continue

            if item < 0 or item >= num_metadata_ingredients:
                decisions_by_output_index[output_index] = None
                continue

            decisions_by_output_index[output_index] = item

        return decisions_by_output_index

    # Backward compatibility with the old schema.
    decisions = response_json.get("decisions", [])
    if not isinstance(decisions, list):
        return decisions_by_output_index

    for position, decision in enumerate(decisions):
        if isinstance(decision, dict):
            output_index = decision.get("output_index", position)
            metadata_index = decision.get("metadata_index")
        else:
            output_index = position
            metadata_index = decision

        if isinstance(output_index, bool) or not isinstance(output_index, int):
            continue
        if output_index < 0 or output_index >= num_output_ingredients:
            continue
        if output_index in decisions_by_output_index:
            continue

        if isinstance(metadata_index, str) and metadata_index.strip().lower() in {
            "null",
            "none",
            "",
        }:
            metadata_index = None

        if metadata_index is None:
            decisions_by_output_index[output_index] = None
            continue

        if isinstance(metadata_index, bool) or not isinstance(metadata_index, int):
            decisions_by_output_index[output_index] = None
            continue

        if metadata_index < 0 or metadata_index >= num_metadata_ingredients:
            decisions_by_output_index[output_index] = None
            continue

        decisions_by_output_index[output_index] = metadata_index

    return decisions_by_output_index


def call_minicpm_for_synonym_decisions(
    sample_id: str,
    output_ingredients: List[str],
    metadata_ingredients: List[str],
) -> Dict[int, Optional[int]]:
    """
    Call MiniCPM once for one dish.

    MiniCPM only returns metadata indices. The local program performs the
    replacement. If all retries fail, all original output words are retained and
    evaluation continues with the next sample.
    """
    user_prompt = build_synonym_prompt(
        sample_id=sample_id,
        output_ingredients=output_ingredients,
        metadata_ingredients=metadata_ingredients,
    )

    last_error: Optional[Exception] = None

    for attempt in range(1, MAX_API_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {
                        "role": "system",
                        "content": SYNONYM_SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": user_prompt,
                    },
                ],
                temperature=0.0,
            )

            response_content = response.choices[0].message.content
            if not isinstance(response_content, str):
                response_content = str(response_content)

            response_json = extract_synonym_response(response_content)

            return parse_synonym_decisions(
                response_json=response_json,
                num_output_ingredients=len(output_ingredients),
                num_metadata_ingredients=len(metadata_ingredients),
            )

        except Exception as exc:
            last_error = exc
            print(
                f"MiniCPM request or response parsing failed for {sample_id} "
                f"(attempt {attempt}/{MAX_API_RETRIES}): {exc}"
            )

            if attempt < MAX_API_RETRIES:
                time.sleep(RETRY_DELAY_SECONDS)

    print(
        f"Warning: MiniCPM synonym analysis failed for {sample_id} after "
        f"{MAX_API_RETRIES} attempts. All original output words will be retained. "
        f"Last error: {last_error}"
    )
    return {}


def build_replacement_map(
    output_ingredients: List[str],
    metadata_ingredients: List[str],
    decisions_by_output_index: Dict[int, Optional[int]],
) -> Tuple[Dict[str, str], List[Dict[str, Any]]]:
    """
    Build a local replacement map.

    Logic for every original output word:
      - metadata_index is valid -> replace with the exact metadata word.
      - metadata_index is null, missing, or invalid -> retain the original word.
    """
    replacement_map: Dict[str, str] = {}
    replacement_details: List[Dict[str, Any]] = []

    for output_index, original_word in enumerate(output_ingredients):
        metadata_index = decisions_by_output_index.get(output_index)

        if metadata_index is None:
            replacement_map[original_word] = original_word
            replacement_details.append(
                {
                    "original_output": original_word,
                    "replacement": original_word,
                    "metadata_match": None,
                    "replaced": False,
                }
            )
            continue

        metadata_word = metadata_ingredients[metadata_index]
        replacement_map[original_word] = metadata_word
        replacement_details.append(
            {
                "original_output": original_word,
                "replacement": metadata_word,
                "metadata_match": metadata_word,
                "replaced": original_word != metadata_word,
            }
        )

    return replacement_map, replacement_details


def apply_replacement_map(
    predicted_set: Set[str],
    replacement_map: Dict[str, str],
) -> Set[str]:
    """
    Replace synonyms with exact metadata words and retain all unmatched words.
    """
    return {
        replacement_map.get(predicted_item, predicted_item)
        for predicted_item in predicted_set
    }


# =========================
# Original metric calculation
# =========================
def compute_set_metrics(
    predicted_set: Set[str],
    ground_truth_set: Set[str],
) -> Dict[str, Any]:
    """
    Compute the original exact-set metrics.

    MiniCPM has already normalized synonyms in predicted_set.
    From this point onward, the original evaluation logic is unchanged.
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


def compute_micro_metrics(
    total_tp: int,
    total_fp: int,
    total_fn: int,
) -> Dict[str, float]:
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
    Evaluate ingredient estimation after MiniCPM synonym replacement.

    For every valid dish:
      1. Read one prediction item and the metadata item with the same id.
      2. Merge all unique predicted ingredients from the original output.
      3. Call MiniCPM once to decide whether each output word has an
         equivalent metadata word.
      4. If equivalent, replace the output word with the exact metadata word.
         Otherwise, retain the original output word.
      5. Apply the same replacement map to every original prediction scope.
      6. Compute the original exact-set metrics locally.
      7. Aggregate the original micro and macro metrics.
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

    missing_prediction_ids: List[str] = []
    invalid_ground_truth_ids: List[str] = []

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

    total_metadata_samples = len(metadata_map)

    for sample_index, (sample_id, meta_item) in enumerate(
        metadata_map.items(),
        start=1,
    ):
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
                    "original_prediction": None,
                    "prediction": None,
                    "synonym_replacements": None,
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
                    "original_prediction": None,
                    "prediction": None,
                    "synonym_replacements": None,
                    "metrics": None,
                }
            )
            continue

        original_predicted_sets: Dict[str, Set[str]] = {}

        for key in pred_keys:
            original_predicted_sets[key] = normalize_ingredient_list(
                pred_item.get(key)
            )

        original_all_predicted_set: Set[str] = set()

        for key in pred_keys:
            original_all_predicted_set.update(original_predicted_sets[key])

        original_predicted_sets["all_ingredients"] = original_all_predicted_set

        # One MiniCPM call per dish. Every unique output word is analyzed once.
        output_ingredients = sorted(original_all_predicted_set)
        metadata_ingredients = sorted(ground_truth_set)

        print(
            f"[{sample_index}/{total_metadata_samples}] "
            f"Analyzing synonyms for {sample_id} with MiniCPM..."
        )

        decisions_by_output_index = call_minicpm_for_synonym_decisions(
            sample_id=sample_id,
            output_ingredients=output_ingredients,
            metadata_ingredients=metadata_ingredients,
        )

        replacement_map, replacement_details = build_replacement_map(
            output_ingredients=output_ingredients,
            metadata_ingredients=metadata_ingredients,
            decisions_by_output_index=decisions_by_output_index,
        )

        corrected_predicted_sets: Dict[str, Set[str]] = {}

        for key in pred_keys:
            corrected_predicted_sets[key] = apply_replacement_map(
                predicted_set=original_predicted_sets[key],
                replacement_map=replacement_map,
            )

        corrected_all_predicted_set: Set[str] = set()

        for key in pred_keys:
            corrected_all_predicted_set.update(corrected_predicted_sets[key])

        corrected_predicted_sets["all_ingredients"] = corrected_all_predicted_set

        sample_metrics: Dict[str, Any] = {}

        for scope in evaluation_scopes:
            metrics = compute_set_metrics(
                predicted_set=corrected_predicted_sets[scope],
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
                "original_prediction": {
                    scope: sorted(original_predicted_sets[scope])
                    for scope in evaluation_scopes
                },
                "prediction": {
                    scope: sorted(corrected_predicted_sets[scope])
                    for scope in evaluation_scopes
                },
                "synonym_replacements": replacement_details,
                "metrics": sample_metrics,
            }
        )

    summary_by_scope: Dict[str, Any] = {}

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
    prediction_json_path = "./outputs/ingredients_results_with_metrics_MiniCPM-V-4.6-Instruct.json"
    metadata_json_path = "./data/ingredient/ingredient_metadata.json"
    output_json_path = "./outputs/ingredient_eval_results.json"

    evaluate_ingredient_estimation(
        prediction_json_path=prediction_json_path,
        metadata_json_path=metadata_json_path,
        output_json_path=output_json_path,
    )
