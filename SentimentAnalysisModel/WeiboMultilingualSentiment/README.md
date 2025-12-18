# Multilingual Sentiment Analysis - Multilingual Sentiment Analysis

This module uses the multilingual sentiment analysis model on HuggingFace for sentiment analysis, supporting 22 languages.

## Model information

- **Model name**: tabularisai/multilingual-sentiment-analysis
- **Base Model**: distilbert-base-multilingual-cased
- **Supported Languages**: 22 languages, including:
- Chinese (中文)
- English
- Español (Spanish)
- Japanese (Japanese)
- 한국어 (Korean)
- Français (French)
- Deutsch (German)
- Русский (Russian)
- العربية (Arabic)
- हिन्दी (Hindi)
- Português (Portuguese)
- Italiano (Italian)
- etc...

- **Output Category**: 5-level emotion classification
- Very Negative
- Negative
- Neutral
-Positive
- Very Positive

## Quick Start

1. Make sure the dependencies are installed:
```bash
pip install transformers torch
```

2. Run the forecast program:
```bash
python predict.py
```

3. Enter text in any language for analysis:
```
Please enter text: I love this product!
Prediction: Very Positive (Confidence: 0.9456)
```

4. View multilingual examples:
```
Please enter text: demo
```

## Code Example

```python
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

#Load model
model_name = "tabularisai/multilingual-sentiment-analysis"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSequenceClassification.from_pretrained(model_name)

# predict
texts = [
"I'm in a good mood today", #中文
"I love this!", # in English
"¡Me encanta!" # Spanish
]

for text in texts:
    inputs = tokenizer(text, return_tensors="pt")
    outputs = model(**inputs)
    prediction = torch.argmax(outputs.logits, dim=1).item()
sentiment_map = {0: "Very negative", 1: "Negative", 2: "Neutral", 3: "Positive", 4: "Very positive"}
    print(f"{text} -> {sentiment_map[prediction]}")
```

## Features

- **Multi-language support**: No need to specify a language, automatically recognizes 22 languages
- **Level 5 Fine Classification**: More detailed sentiment analysis than traditional two-level classification
- **High Accuracy**: Advanced architecture based on DistilBERT
- **Local cache**: Save it locally after the first download to speed up subsequent use.

## Application scenarios

- International social media monitoring
- Multilingual customer feedback analysis
- Global product review sentiment classification
- Cross-language brand sentiment tracking
- Multi-language customer service optimization
- International market research

## Model storage

- The model will be automatically downloaded to the `model` folder in the current directory when running for the first time.
- Subsequent runs will be loaded directly from local, no need to download again
- The model size is about 135MB, and an internet connection is required for the first download.

## File description

- `predict.py`: main prediction program, using direct model calls
- `README.md`: instructions for use

## Notes

- The model will be automatically downloaded when running for the first time, and an Internet connection is required
- The model will be saved to the current directory for subsequent use.
- Supports GPU acceleration and automatically detects available devices
- If you need to clean up the model files, delete the `model` folder
- The model is trained based on synthetic data and is recommended for verification in practical applications.