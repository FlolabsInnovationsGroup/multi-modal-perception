# MiniCPM Test Cases

This repository contains test cases for MiniCPM. For the design goals, test coverage, and implementation approach, refer to the [Notion document](https://app.notion.com/p/flolabsrd/Create-test-cases-376a1576955180f5aea5c41b6bee755c?source=copy_link).

## Dataset

Download the required dataset from [Google Drive](https://drive.google.com/file/d/16-CvPPOci1fVAPghEwj-41vAKaUtImtg/view?usp=drive_link).

## Image Tests

Run the scripts in the following order:

```bash
python test_case_image.py
python eval_food_calories.py
python eval_ingredients.py
python ingredient_eval_with_minicpm.py
```

`test_case_image.py` supports calorie estimation and ingredient prediction. Update the dataset path in the `main` section before running it.

`ingredient_eval_with_minicpm.py` uses MiniCPM to normalize synonyms between the generated output and the metadata.

`test_case_image.py` uses the MiniCPM API rather than a cloud deployment. It can be used directly for local testing, but the current API does not support combined image and audio input.

## Jarvis GPU Tests

The `test_jarvis_gpu` directory contains scripts for running MiniCPM deployed on Jarvis GPU:

* `test_case_image_audio.py`: image and audio input
* `test_case_image_text.py`: image and text input

Model inference and evaluation are separated. Inference runs in the cloud, while evaluation runs locally, since evaluation logic may require frequent updates and is easier to modify locally.

## Audio Test

`test_case_audio.py` uses audio and text input for speech recognition. It includes both model inference and evaluation.

## Future Work

Add an automation script to:

1. Upload code to Jarvis.
2. Run the test scripts.
3. Shut down the Jarvis instance after completion.
