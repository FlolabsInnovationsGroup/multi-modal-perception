import asyncio
import base64
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import miniaudio
import numpy as np
import pandas as pd
import websockets
from tqdm import tqdm


# ============================================================
# CONFIG
# ============================================================

# You are inside:
# C:\Users\USER\Downloads\loquacious_test_dataset
DATASET_DIR = Path(".")

WS_URL = "wss://minicpmo45.modelbest.cn/v1/realtime?mode=audio"

OUTPUT_DIR = Path("./minicpm_o45_eval_results")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

RESULTS_CSV = OUTPUT_DIR / "results.csv"
SUMMARY_JSON = OUTPUT_DIR / "wer_summary.json"

# Start with 1 sample.
# After the output looks correct, change to None for all 100.
LIMIT = None

# Set False so old bad results are not reused.
RESUME = False

# Required API audio format
TARGET_SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_SECONDS = 1.0
CHUNK_SAMPLES = int(TARGET_SAMPLE_RATE * CHUNK_SECONDS)
CHUNK_BYTES = CHUNK_SAMPLES * 4  # float32

# Important:
# This API is realtime. Keep this at 1.0 for correct testing.
SEND_CHUNK_SLEEP_SECONDS = 1.0

# Wait settings after sending the clip
MIN_AFTER_AUDIO_WAIT_SECONDS = 5.0
IDLE_AFTER_TEXT_SECONDS = 8.0
MAX_AFTER_AUDIO_WAIT_SECONDS = 90.0

# Connection retry settings
MAX_CONNECT_RETRIES = 5
CONNECT_TIMEOUT_SECONDS = 90
QUEUE_TIMEOUT_SECONDS = 180
SESSION_CREATED_TIMEOUT_SECONDS = 120
BETWEEN_CLIPS_SLEEP_SECONDS = 8.0


# ============================================================
# DATASET HELPERS
# ============================================================

def check_dataset_structure(dataset_dir: Path) -> None:
    metadata_path = dataset_dir / "metadata.json"
    clips_dir = dataset_dir / "clips"
    prompt_dir = dataset_dir / "prompt"

    if not metadata_path.exists():
        raise FileNotFoundError(f"metadata.json not found: {metadata_path.resolve()}")

    if not clips_dir.exists():
        raise FileNotFoundError(f"clips folder not found: {clips_dir.resolve()}")

    if not prompt_dir.exists():
        raise FileNotFoundError(f"prompt folder not found: {prompt_dir.resolve()}")

    print("Dataset structure found:")
    print("metadata:", metadata_path.resolve())
    print("clips:", clips_dir.resolve())
    print("prompt:", prompt_dir.resolve())


def load_metadata(dataset_dir: Path) -> List[Dict[str, Any]]:
    metadata_path = dataset_dir / "metadata.json"

    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    if not isinstance(metadata, list):
        raise ValueError("metadata.json must contain a list of objects.")

    return metadata


def get_ground_truth(item: Dict[str, Any]) -> str:
    return (
        item.get("transcription")
        or item.get("transcirption")
        or item.get("transcript")
        or item.get("text")
        or ""
    )


def get_clip_path(dataset_dir: Path, item: Dict[str, Any]) -> Path:
    clip_path_value = item.get("clip_path")

    if not clip_path_value:
        raise ValueError(f"Missing clip_path in metadata item: {item}")

    clip_path = dataset_dir / clip_path_value

    if not clip_path.exists() and clip_path.suffix == "":
        mp3_path = clip_path.with_suffix(".mp3")
        if mp3_path.exists():
            return mp3_path

    if not clip_path.exists():
        raise FileNotFoundError(f"Audio clip not found: {clip_path.resolve()}")

    return clip_path


def get_prompt_text(dataset_dir: Path, item: Dict[str, Any]) -> str:
    if item.get("prompt_path"):
        prompt_path = dataset_dir / item["prompt_path"]
    else:
        prompt_path = dataset_dir / "prompt" / f"{item['id']}.txt"

    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path.resolve()}")

    return prompt_path.read_text(encoding="utf-8").strip()


# ============================================================
# AUDIO DECODING WITHOUT FFMPEG
# ============================================================

def convert_audio_to_float32_pcm_bytes(audio_path: Path) -> bytes:
    decoded = miniaudio.decode_file(
        str(audio_path),
        output_format=miniaudio.SampleFormat.FLOAT32,
        nchannels=CHANNELS,
        sample_rate=TARGET_SAMPLE_RATE,
    )

    return decoded.samples.tobytes()


def chunk_pcm_bytes(pcm_bytes: bytes) -> List[bytes]:
    chunks = []

    for start in range(0, len(pcm_bytes), CHUNK_BYTES):
        chunk = pcm_bytes[start:start + CHUNK_BYTES]

        if len(chunk) < CHUNK_BYTES:
            chunk += b"\x00" * (CHUNK_BYTES - len(chunk))

        chunks.append(chunk)

    return chunks


def b64_audio(raw_pcm_bytes: bytes) -> str:
    return base64.b64encode(raw_pcm_bytes).decode("utf-8")


# ============================================================
# MODEL OUTPUT PARSING
# ============================================================

def extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    text = str(text or "").strip()

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    match = re.search(r"\{.*?\}", text, flags=re.DOTALL)

    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    return None


def extract_transcript(model_output: str) -> str:
    parsed = extract_json_object(model_output)

    if parsed and "transcript" in parsed:
        return str(parsed["transcript"]).strip()

    return str(model_output or "").strip()


# ============================================================
# WER
# ============================================================

def normalize_for_wer(text: str) -> str:
    text = str(text or "").lower()
    text = re.sub(r"[^\w\s']", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def split_words(text: str) -> List[str]:
    clean = normalize_for_wer(text)
    return clean.split() if clean else []


def edit_distance(ref_words: List[str], hyp_words: List[str]) -> int:
    n = len(ref_words)
    m = len(hyp_words)

    dp = [[0] * (m + 1) for _ in range(n + 1)]

    for i in range(n + 1):
        dp[i][0] = i

    for j in range(m + 1):
        dp[0][j] = j

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if ref_words[i - 1] == hyp_words[j - 1] else 1

            dp[i][j] = min(
                dp[i - 1][j] + 1,
                dp[i][j - 1] + 1,
                dp[i - 1][j - 1] + cost,
            )

    return dp[n][m]


def word_error_rate(reference: str, hypothesis: str) -> float:
    ref = split_words(reference)
    hyp = split_words(hypothesis)

    if len(ref) == 0:
        return 0.0 if len(hyp) == 0 else 1.0

    return edit_distance(ref, hyp) / len(ref)


def total_word_error_stats(rows: List[Dict[str, Any]]) -> Tuple[int, int, float]:
    total_errors = 0
    total_ref_words = 0

    for row in rows:
        ref_words = split_words(row.get("ground_truth", ""))
        hyp_words = split_words(row.get("prediction", ""))

        total_errors += edit_distance(ref_words, hyp_words)
        total_ref_words += len(ref_words)

    if total_ref_words == 0:
        return total_errors, total_ref_words, 0.0

    return total_errors, total_ref_words, total_errors / total_ref_words


# ============================================================
# WEBSOCKET HELPERS
# ============================================================

async def recv_json(ws, timeout: float) -> Dict[str, Any]:
    raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
    return json.loads(raw)


async def wait_for_queue_done(ws) -> None:
    while True:
        event = await recv_json(ws, timeout=QUEUE_TIMEOUT_SECONDS)
        event_type = event.get("type")

        if event_type == "session.queue_done":
            return

        if event_type == "session.queued":
            print(
                f"Queued. position={event.get('position')} "
                f"estimated_wait_s={event.get('estimated_wait_s')}"
            )

        elif event_type == "session.queue_update":
            print(
                f"Queue update. position={event.get('position')} "
                f"estimated_wait_s={event.get('estimated_wait_s')}"
            )

        elif event_type == "error":
            raise RuntimeError(f"API error while waiting for queue: {event}")


async def wait_for_session_created(ws) -> None:
    while True:
        event = await recv_json(ws, timeout=SESSION_CREATED_TIMEOUT_SECONDS)
        event_type = event.get("type")

        if event_type == "session.created":
            return

        if event_type == "error":
            raise RuntimeError(f"API error during session creation: {event}")


# ============================================================
# MINICPM-O 4.5 TRANSCRIPTION
# ============================================================

async def transcribe_one_clip_once(audio_path: Path, prompt_text: str) -> str:
    pcm_bytes = convert_audio_to_float32_pcm_bytes(audio_path)
    chunks = chunk_pcm_bytes(pcm_bytes)
    silence_chunk = np.zeros(CHUNK_SAMPLES, dtype=np.float32).tobytes()

    collected_text_parts = []

    state = {
        "got_text": False,
        "listen_after_text": False,
        "last_text_time": None,
        "closed": False,
        "error": None,
    }

    stop_sending = asyncio.Event()
    real_audio_sent = asyncio.Event()

    async with websockets.connect(
        WS_URL,
        open_timeout=CONNECT_TIMEOUT_SECONDS,
        close_timeout=20,
        ping_interval=20,
        ping_timeout=30,
        max_size=100 * 1024 * 1024,
    ) as ws:

        await wait_for_queue_done(ws)

        system_prompt = (
            prompt_text
            + "\n\nYou will receive one audio clip. "
            + "Transcribe all spoken words from the complete audio clip. "
            + "Do not stop after the first phrase. "
            + "Return only the requested JSON object. "
            + "Do not explain, summarize, translate, or add extra text."
        )

        await ws.send(json.dumps({
            "type": "session.init",
            "payload": {
                "system_prompt": system_prompt,
                "config": {
                    "length_penalty": 1.0
                }
            }
        }))

        await wait_for_session_created(ws)

        async def receiver():
            while True:
                try:
                    event = await recv_json(ws, timeout=MAX_AFTER_AUDIO_WAIT_SECONDS)
                    event_type = event.get("type")

                    if event_type == "response.output.delta":
                        kind = event.get("kind")

                        if kind == "text":
                            text_piece = event.get("text", "")
                            if text_piece:
                                collected_text_parts.append(text_piece)
                                state["got_text"] = True
                                state["listen_after_text"] = False
                                state["last_text_time"] = time.time()

                        elif kind == "listen":
                            if state["got_text"]:
                                state["listen_after_text"] = True

                    elif event_type == "session.closed":
                        state["closed"] = True
                        break

                    elif event_type == "error":
                        state["error"] = str(event)
                        break

                except asyncio.TimeoutError:
                    break

                except websockets.ConnectionClosed:
                    state["closed"] = True
                    break

        async def sender():
            # The server's turn detection expects a continuous audio feed,
            # like a live microphone. Sending nothing after the clip ends
            # (as before) leaves it waiting forever for more input, since it
            # never gets a chance to observe trailing silence. Keep the
            # stream alive with silence chunks until told to stop.
            for chunk in chunks:
                if stop_sending.is_set():
                    return

                await ws.send(json.dumps({
                    "type": "input.append",
                    "input": {
                        "audio": b64_audio(chunk),
                        "force_listen": False
                    }
                }))

                await asyncio.sleep(SEND_CHUNK_SLEEP_SECONDS)

            real_audio_sent.set()

            while not stop_sending.is_set():
                await ws.send(json.dumps({
                    "type": "input.append",
                    "input": {
                        "audio": b64_audio(silence_chunk),
                        "force_listen": False
                    }
                }))

                await asyncio.sleep(SEND_CHUNK_SLEEP_SECONDS)

        receiver_task = asyncio.create_task(receiver())
        sender_task = asyncio.create_task(sender())

        print(f"Sending {audio_path.name} in realtime chunks. chunks={len(chunks)}")

        try:
            await real_audio_sent.wait()

            start_wait = time.time()

            while True:
                if state["error"]:
                    raise RuntimeError(state["error"])

                now = time.time()
                elapsed = now - start_wait

                if elapsed < MIN_AFTER_AUDIO_WAIT_SECONDS:
                    await asyncio.sleep(0.25)
                    continue

                if elapsed > MAX_AFTER_AUDIO_WAIT_SECONDS:
                    break

                if state["got_text"] and state["last_text_time"] is not None:
                    idle_time = now - state["last_text_time"]

                    if idle_time >= IDLE_AFTER_TEXT_SECONDS:
                        break

                    if state["listen_after_text"] and idle_time >= 3.0:
                        break

                await asyncio.sleep(0.25)

        finally:
            stop_sending.set()

            try:
                await ws.send(json.dumps({
                    "type": "session.close",
                    "reason": "evaluation_done"
                }))
            except Exception:
                pass

            await asyncio.sleep(1.0)

            sender_task.cancel()
            receiver_task.cancel()

            for task in (sender_task, receiver_task):
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    return "".join(collected_text_parts).strip()


async def transcribe_one_clip(audio_path: Path, prompt_text: str) -> str:
    last_error = None

    for attempt in range(1, MAX_CONNECT_RETRIES + 1):
        try:
            print(f"Connection attempt {attempt}/{MAX_CONNECT_RETRIES}")
            return await transcribe_one_clip_once(audio_path, prompt_text)

        except Exception as e:
            last_error = e
            print(f"Attempt failed: {e}")

            if attempt < MAX_CONNECT_RETRIES:
                sleep_seconds = 5 * attempt
                print(f"Retrying after {sleep_seconds} seconds...")
                await asyncio.sleep(sleep_seconds)

    raise RuntimeError(f"All attempts failed for {audio_path}") from last_error


# ============================================================
# EVALUATION LOOP
# ============================================================

async def evaluate_dataset():
    check_dataset_structure(DATASET_DIR)

    if not RESUME:
        if RESULTS_CSV.exists():
            RESULTS_CSV.unlink()
        if SUMMARY_JSON.exists():
            SUMMARY_JSON.unlink()

    metadata = load_metadata(DATASET_DIR)

    if LIMIT is not None:
        metadata = metadata[:LIMIT]

    print(f"\nSamples to test: {len(metadata)}")
    print(f"Results CSV: {RESULTS_CSV.resolve()}")
    print("Realtime mode is enabled. This sends audio at real playback speed.\n")

    existing_results = []

    if RESUME and RESULTS_CSV.exists():
        existing_df = pd.read_csv(RESULTS_CSV)
        existing_results = existing_df.to_dict("records")
        done_ids = set(existing_df["id"].astype(str).tolist())
        print(f"Resume mode. Found {len(done_ids)} completed samples.")
    else:
        done_ids = set()

    results = existing_results[:]

    for item in tqdm(metadata, desc="Testing MiniCPM-o 4.5"):
        sample_id = str(item["id"])

        if sample_id in done_ids:
            continue

        clip_path = get_clip_path(DATASET_DIR, item)
        prompt_text = get_prompt_text(DATASET_DIR, item)
        ground_truth = get_ground_truth(item)
        sample_type = item.get("sample_type", "unknown")

        print("\n" + "=" * 70)
        print("ID:", sample_id)
        print("Type:", sample_type)
        print("Clip:", clip_path)
        print("=" * 70)

        start_time = time.time()

        try:
            raw_model_output = await transcribe_one_clip(
                audio_path=clip_path,
                prompt_text=prompt_text,
            )

            prediction = extract_transcript(raw_model_output)
            sample_wer = word_error_rate(ground_truth, prediction)
            error = ""

        except Exception as e:
            raw_model_output = ""
            prediction = ""
            sample_wer = None
            error = str(e)

        elapsed_seconds = round(time.time() - start_time, 2)

        row = {
            "id": sample_id,
            "sample_type": sample_type,
            "clip_path": str(item.get("clip_path", "")),
            "prompt_path": str(item.get("prompt_path", "")),
            "ground_truth": ground_truth,
            "prediction": prediction,
            "raw_model_output": raw_model_output,
            "ground_truth_clean": normalize_for_wer(ground_truth),
            "prediction_clean": normalize_for_wer(prediction),
            "wer": sample_wer,
            "elapsed_seconds": elapsed_seconds,
            "error": error,
        }

        results.append(row)

        pd.DataFrame(results).to_csv(
            RESULTS_CSV,
            index=False,
            encoding="utf-8-sig"
        )

        print("Ground truth:", ground_truth)
        print("Prediction:", prediction)
        print("Raw model output:", raw_model_output)
        print("WER:", sample_wer)
        print("Elapsed seconds:", elapsed_seconds)

        if error:
            print("ERROR:", error)

        await asyncio.sleep(BETWEEN_CLIPS_SLEEP_SECONDS)

    results_df = pd.DataFrame(results)

    successful_df = results_df[
        results_df["wer"].notna()
        & results_df["error"].fillna("").astype(str).eq("")
    ].copy()

    if len(successful_df) == 0:
        raise RuntimeError("No successful samples. The API may be unavailable or the queue may be timing out.")

    successful_rows = successful_df.to_dict("records")
    total_errors, total_ref_words, overall_wer = total_word_error_stats(successful_rows)

    summary = {
        "num_requested": int(len(metadata)),
        "num_results_rows": int(len(results_df)),
        "num_successful": int(len(successful_df)),
        "num_failed": int(len(results_df) - len(successful_df)),
        "total_word_errors": int(total_errors),
        "total_reference_words": int(total_ref_words),
        "overall_wer": float(overall_wer),
        "average_sample_wer": float(successful_df["wer"].mean()),
        "by_sample_type": {}
    }

    for sample_type, group in successful_df.groupby("sample_type"):
        group_rows = group.to_dict("records")
        group_errors, group_ref_words, group_overall_wer = total_word_error_stats(group_rows)

        summary["by_sample_type"][sample_type] = {
            "num_samples": int(len(group)),
            "total_word_errors": int(group_errors),
            "total_reference_words": int(group_ref_words),
            "overall_wer": float(group_overall_wer),
            "average_sample_wer": float(group["wer"].mean()),
        }

    with open(SUMMARY_JSON, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 70)
    print("DONE")
    print("=" * 70)
    print("Results CSV:", RESULTS_CSV.resolve())
    print("Summary JSON:", SUMMARY_JSON.resolve())
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(evaluate_dataset())