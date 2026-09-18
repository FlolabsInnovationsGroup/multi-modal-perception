# Dataset

This directory contains the datasets used for MiniCPM multimodal test cases.

The dataset files are not included in this repository due to size limitations.

## Download

Download the required dataset from:

Google Drive:
https://drive.google.com/file/d/16-CvPPOci1fVAPghEwj-41vAKaUtImtg/view?usp=drive_link


## Directory Structure

After downloading and extracting the dataset, place the files under this directory with the following structure:


data/
│
├── food_calories/
│ │
│ ├── images/
│ │ ├── calorie_000001.jpg
│ │ ├── calorie_000002.jpg
│ │ └── ...
│ │
│ └── prompts/
│ ├── calorie_000001.txt
│ ├── calorie_000002.txt
│ └── ...
│
└── audio/
│
└── ...



## Food Calorie Dataset

The food calorie evaluation uses:


data/food_calories/images/


for input images and:


data/food_calories/prompts/


for corresponding prompts.

Each image should have a matching prompt file with the same ID:

Example:


images/calorie_000001.jpg
prompts/calorie_000001.txt



## Usage

The dataset path is referenced by the test servers and evaluation scripts.

Example:


image_dir:
data/food_calories/images

prompt_dir:
data/food_calories/prompts


The inference server generates model outputs, while evaluation scripts process the generated results.


## Notes

- Do not commit dataset files into GitHub.
- Keep the dataset directory structure unchanged after downloading.
- Generated outputs should be stored under `outputs/` rather than this directory.