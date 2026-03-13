# Caipo Multimodal Dataset

A unified multimodal dataset for training vision-language and dialogue models across seven tasks: calorie estimation, scene analysis, captioning, visual QA, nutrition/ingredients, conversation identity, and dialogue summarization.

## Dataset structure

```
caipo_multimodal_dataset/
├── README.md
├── unified_train.jsonl          # Single training file (all tasks shuffled)
├── unified_val.jsonl           # Single validation file
├── tasks/
│   ├── food_calories/          # Calorie estimation
│   │   ├── images/
│   │   └── annotations.jsonl
│   ├── environment_scene/      # Scene analysis & hazards
│   │   ├── images/
│   │   └── annotations.jsonl
│   ├── captioning/             # Image captioning
│   │   ├── images/
│   │   └── annotations.jsonl
│   ├── visual_qa/              # Visual question answering
│   │   ├── images/
│   │   └── annotations.jsonl
│   ├── nutrition_ingredients/  # Ingredients & dietary (e.g. vegan)
│   │   ├── images/
│   │   └── annotations.jsonl
│   ├── conversation_identity/  # Last speaker tracking
│   │   ├── dialogues/
│   │   └── annotations.jsonl
│   └── dialogue_summarization/ # Summarize conversation
│       ├── dialogues/
│       └── annotations.jsonl
└── scripts/
    ├── generate_unified.py     # Merge task annotations into unified_*.jsonl
    └── load_dataset.py        # HuggingFace-style loader example
```

## Tasks

|---------------------------|--------------|-----------------------------------------------------------------------------------------------|
| Task                      | Modality     | Description |
|---------------------------|--------------|-----------------------------------------------------------------------------------------------|
| **food_calories**         | Image + text | Estimate calories from food images. `image_path` relative to task dir.                        |
| **environment_scene**     | Image + text | Describe environment and hazards. `image_path` relative to task dir.                          |
| **captioning**            | Image + text | Describe the image in one sentence. `image_path` relative to task dir.                        |
| **visual_qa**             | Image + text | Answer a question about the image (e.g. count, color). `image_path` relative to task dir.     |
| **nutrition_ingredients** | Image + text | List ingredients or answer dietary questions (e.g. vegan). `image_path` relative to task dir. |
| **conversation_identity** | Text only    | Multi-turn dialogues; answer "Who was the last person that talked to me?". `context_path`     |
|                                            points to dialogue JSON.                                                                      |
| **dialogue_summarization**| Text only    | Summarize the conversation in 1–2 sentences. `context_path` points to dialogue JSON.          |
|---------------------------|--------------|-----------------------------------------------------------------------------------------------|

## Annotation format

- **Image tasks** (food_calories, environment_scene, captioning, visual_qa, nutrition_ingredients): each line in `annotations.jsonl` is:
  ```json
  {"image_path": "images/<name>.jpg", "instruction": "...", "response": "..."}
  ```
- **Dialogue tasks** (conversation_identity, dialogue_summarization): each line is:
  ```json
  {"context_path": "dialogues/chat_001.json", "instruction": "...", "response": "..."}
  ```
  Dialogue files under `dialogues/` use: `{"turns": [{"speaker": "user"|"Alice"|..., "text": "..."}, ...]}`.

## Suggested external datasets

Public datasets you can use to expand each task (convert to this repo’s annotation format and add images/dialogues as needed):

|---------------------------|-----------------|----------------------------------------------------------------------------------------------------------|
| Task                      | Dataset         | Link                                                                                                     |
|---------------------------|-----------------|----------------------------------------------------------------------------------------------------------|
| **food_calories**         | Nutrition5k     | https://github.com/google-research-datasets/Nutrition5k                                                  |
|                           | FooDD           | https://ieee-dataport.org/open-access/foodd-food-detection-dataset-calorie-measurement-using-food-images |
|                           | ECUSTFD         | https://arxiv.org/abs/1705.07632                                                                         |
| **environment_scene**     | HomeSafeBench   | https://arxiv.org/abs/2509.23690                                                                         |
|                           | ACDC            | https://acdc.vision.ee.ethz.ch/                                                                          |
| **captioning**            | COCO Captions   | https://cocodataset.org/                                                                                 |
|                           | Flickr30k       | https://www.kaggle.com/datasets/hsankesara/flickr-image-dataset (or Zenodo/Hugging Face)                 |
| **visual_qa**             | VQA v2          | https://visualqa.org/                                                                                    |
|                           | GQA             | https://cs.stanford.edu/people/dorarad/gqa/download.html                                                 |
| **nutrition_ingredients** | Nutrition5k     | https://github.com/google-research-datasets/Nutrition5k                                                  |
|                           | NutriGreen      | https://www.frontiersin.org/articles/10.3389/fnut.2024.1342823/full                                      |
|                           | Open Food Facts | https://world.openfoodfacts.org/                                                                         |
| **conversation_identity** | ReDial          | https://redialdata.github.io/                                                                            |
|                           | DDRel           | https://github.com/JiaQiSJTU/DialogueRelationClassification                                              |
| **dialogue_summarization**| SAMSum          | https://huggingface.co/datasets/samsum                                                                   |
|                           | DialogSum       | https://huggingface.co/datasets/cynlp/dialogsum                                                          |
|---------------------------|-----------------|----------------------------------------------------------------------------------------------------------|
## Stats

- **unified_train.jsonl**: total training examples (all tasks).
- **unified_val.jsonl**: total validation examples (all tasks).
- Run `scripts/generate_unified.py` to (re)generate unified files from task `annotations.jsonl`.

## Usage

1. **Generate unified splits** (after editing task annotations):
   ```bash
   python scripts/generate_unified.py
   ```
2. **Load for training** (example):
   ```bash
   python scripts/load_dataset.py
   ```
   Or use the loader logic in your training pipeline; see `scripts/load_dataset.py` for paths and field names.

## License

See repository license.


