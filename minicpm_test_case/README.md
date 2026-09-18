# MiniCPM-V Food Calorie Evaluation

A multimodal food analysis pipeline based on **MiniCPM-V-4.6**.

This project provides image-text and image-audio inference services
deployed on JarvisLabs GPU, together with evaluation scripts for food
calorie estimation and ingredient analysis.

## Features

### Image-Text Inference

Input: - Food image - Text prompt

Output: - Model-generated response - Structured JSON result for
evaluation tasks

### Image-Audio Pipeline

The current audio pipeline uses:

    Audio
    |
    v
    Whisper transcription
    |
    v
    Text + Image
    |
    v
    MiniCPM-V-4.6
    |
    v
    Response

It supports food-related image and audio question answering.

## Project Structure

    MiniCPM-V-food-calorie/

    ├── server/
    │   ├── server.py
    │   ├── client.py
    │   ├── demo_multimodal_inference.py
    │   ├── test_case_image_text_server.py
    │   └── test_case_image_audio_server.py
    │
    ├── evaluation/
    │   ├── eval_food_calories.py
    │   └── eval_ingredients.py
    │
    ├── data/
    │   └── README.md
    │
    ├── outputs/
    │   └── .gitkeep
    │
    ├── requirements.txt
    ├── .gitignore
    └── README.md

## Relationship with Original Implementation

The repository contains two parts.

### Original Multimodal API Framework

Provides: - Generic multimodal inference server - Unified client
interface - Example inference script

Files:

    server/
    ├── server.py
    ├── client.py
    └── demo_multimodal_inference.py

### Task-specific Evaluation Pipeline

Extends the original framework with: - Food calorie benchmark testing -
Image-text batch inference - Image-audio processing pipeline -
Evaluation scripts

Files:

    server/
    ├── test_case_image_text_server.py
    └── test_case_image_audio_server.py

    evaluation/
    ├── eval_food_calories.py
    └── eval_ingredients.py

## Environment

Tested configuration:

-   GPU: NVIDIA A30
-   Python: 3.10
-   PyTorch: 2.10.0 + CUDA 12.8
-   Transformers: 5.16.1

Model:

    openbmb/MiniCPM-V-4.6

## MiniCPM-V-4.6 Configuration Note

The current environment requires:

``` python
processor.image_processor.downsample_mode = "4x"
```

The default configuration may cause vision feature reshape errors during
inference.

## Deployment on JarvisLabs GPU

Workflow:

1.  Start JarvisLabs GPU instance
2.  Activate the configured Python environment
3.  Launch FastAPI inference server
4.  Send inference requests
5.  Save outputs for evaluation

Example:

``` bash
python server/test_case_image_text_server.py
```

or:

``` bash
python server/test_case_image_audio_server.py
```

## Evaluation

Evaluation scripts:

    evaluation/
    ├── eval_food_calories.py
    └── eval_ingredients.py

Supported tasks: - Food calorie estimation - Ingredient extraction and
comparison

## Current Validation

### Image-Text Pipeline

Validated with local food images.

Pipeline:

    Image + Prompt
          |
          v
    MiniCPM-V-4.6
          |
          v
    JSON response

### Image-Audio Pipeline

Validated with 94 audio samples.

Results: - Total samples: 94 - Successful inference: 94 - Failed
inference: 0

## Limitations

-   Audio pipeline uses speech transcription followed by image-text
    inference.
-   It is not an end-to-end audio-vision foundation model.
-   Calorie estimation results may require additional normalization and
    evaluation.

## Future Work

Possible improvements: - Better structured output parsing - More
evaluation metrics - Containerized deployment - Automated benchmark
pipeline
