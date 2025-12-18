# Weibo sentiment analysis - fine-tuning model based on BertChinese

This module uses the pre-trained Weibo sentiment analysis model on HuggingFace to perform sentiment analysis.

## Model information

- **Model name**: wsqstar/GISchat-weibo-100k-fine-tuned-bert
- **Model type**: BERT Chinese emotion classification model
- **Training data**: 100,000 Weibo data
- **Output**: binary classification (positive/negative emotion)

## How to use

### Method 1: Direct model call (recommended)
```bash
python predict.py
```

### Method 2: Pipeline method
```bash
python predict_pipeline.py
```

## Quick Start

1. Make sure the dependencies are installed:
```bash
pip install transformers torch
```

2. Run the forecast program:
```bash
python predict.py
```

3. Enter Weibo text for analysis:
```
Please enter Weibo content: The weather is so nice today and I am in a great mood!
Prediction: Positive sentiment (Confidence: 0.9234)
```

## Code Example

```python
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

#Load model
model_name = "wsqstar/GISchat-weibo-100k-fine-tuned-bert"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSequenceClassification.from_pretrained(model_name)

# predict
text = "I'm in a good mood today"
inputs = tokenizer(text, return_tensors="pt")
outputs = model(**inputs)
prediction = torch.argmax(outputs.logits, dim=1).item()
print("positive emotion" if prediction == 1 else "negative emotion")
```

## File description

- `predict.py`: main prediction program, using direct model calls
- `predict_pipeline.py`: prediction program using pipeline method
- `README.md`: instructions for use

## Model storage

- The model will be automatically downloaded to the `model` folder in the current directory when running for the first time.
- Subsequent runs will be loaded directly from local, no need to download again
- The model size is about 400MB, and an internet connection is required for the first download.

## Notes

- The model will be automatically downloaded when running for the first time, and an Internet connection is required
- The model will be saved to the current directory for subsequent use.
- Supports GPU acceleration and automatically detects available devices
- If you need to clean up the model files, delete the `model` folder