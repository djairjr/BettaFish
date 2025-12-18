# Weibo emotion recognition model-GPT2-LoRA fine-tuning

## Project description
This is a Weibo emotion binary classification model based on GPT2, using LoRA (Low-Rank Adaptation) fine-tuning technology. LoRA fine-tuning implemented through the PEFT library only requires training a very small number of parameters to adapt the model to sentiment analysis tasks, significantly reducing computing resource requirements and model volume.

## Dataset
The Weibo emotion data set (weibo_senti_100k) is used, which contains about 100,000 pieces of Weibo content with emotional annotations, and about 50,000 positive and negative comments each. Dataset labels:
- Tag 0: Negative emotions
- Tag 1: Positive emotions

## File structure
```
GPT2-Lora/
├── train.py # Training script (LoRA implementation based on PEFT library)
├── predict.py # Prediction script (interactive use)
├── requirements.txt # Dependency package list
├── models/ # Locally stored pre-trained models
│ └── gpt2-chinese/ # Chinese GPT2 model and configuration
├── dataset/ # Dataset directory
│ └── weibo_senti_100k.csv # Weibo emotion data set
└── best_weibo_sentiment_lora/ # Trained LoRA weights (generated after training)
```

## Technical features

1. **Extreme parameter efficiency**: Compared with full parameter fine-tuning, only about 0.1%-1% of parameters are trained.
2. **Use PEFT library**: Based on Hugging Face’s official parameter-efficient fine-tuning library, stable and reliable
3. **Model performance maintenance**: Maintain good classification performance while only training a few parameters.
4. **Deployment-friendly**: LoRA weight files are small, making it easy to deploy and share models.

## LoRA technical advantages

LoRA (Low-Rank Adaptation) is currently the most popular parameter efficient fine-tuning technology:

1. **Ultra-low number of parameters**: Through low-rank decomposition, the large matrix is ​​decomposed into the product of two small matrices
2. **Plug-in design**: LoRA weights can be loaded and unloaded dynamically, and one basic model supports multiple tasks.
3. **Fast training speed**: few parameters, short training time, and small memory usage
4. **Lossless original model**: The weights of the original pre-trained model remain unchanged to avoid catastrophic forgetting.

## Environment dependencies

Install required dependencies:
```bash
pip install -r requirements.txt
```

Main dependency packages:
- Python 3.8+
- PyTorch 1.13+
- Transformers 4.28+
- PEFT 0.4+
- Pandas, NumPy, Scikit-learn

## How to use

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Training model
```bash
python train.py
```

The training process will automatically:
- Download and save the Chinese GPT2 pre-trained model locally
- Load Weibo emotion data set
- Train models using LoRA technology
- Save the best LoRA weights to `./best_weibo_sentiment_lora/`

### 3. Sentiment analysis prediction
```bash
python predict.py
```

After running, you will enter interactive mode:
- Enter the Weibo text to be analyzed in the console
- The system returns sentiment analysis results (positive/negative) and confidence levels
- Enter 'q' to exit the program

## Model configuration

- **Basic model**: `uer/gpt2-chinese-cluecorpussmall` Chinese pre-training model
- **Model local saving path**: `./models/gpt2-chinese/`
- **LoRA Configuration**:
- rank (r): 8 - the rank of the low-rank matrix
- alpha: 32 - scaling factor
- target_modules: ["c_attn", "c_proj"] - target linear layer
- dropout: 0.1 - prevent overfitting

## Performance comparison

| Method | Proportion of trainable parameters | Model file size | Training time | Inference speed |
|------|----------------|--------------|----------|----------|
| Full parameter fine-tuning | 100% | ~500MB | Long | Slow |
| Adapter fine-tuning | ~3% | ~50MB | Medium | Medium |
| **LoRA Fine-tuning** | **~0.5%** | **~2MB** | **Short** | **Fast** |

## Usage example

```
Equipment used: cuda
LoRA model loaded successfully!

============= Weibo Sentiment Analysis (LoRA version) =============
Enter Weibo content for analysis (enter 'q' to exit):

Please enter Weibo content: This movie is so beautiful, I like it very much!
Prediction: Positive sentiment (Confidence: 0.9876)

Please enter Weibo content: Poor service attitude, expensive prices, not recommended at all
Prediction: Negative sentiment (Confidence: 0.9742)

Please enter Weibo content: q
```

## Notes

1. **First run**: The pre-trained model will be automatically downloaded when running `train.py` for the first time, please ensure the network connection
2. **GPU recommendation**: Although LoRA has few parameters, it is recommended to use GPU to accelerate training.
3. **Model loading**: Prediction requires a trained LoRA weight file first
4. **Compatibility**: Based on the PEFT library, fully compatible with the Hugging Face ecosystem

## Extended functions

- **Multi-task support**: Different LoRA weights can be trained for different tasks, sharing the same basic model
- **Weight Merging**: Multiple LoRA weights can be merged, or LoRA weights can be merged into the base model
- **Dynamic Switching**: Supports dynamic loading and switching of different LoRA weights at runtime

## Technical principles

LoRA adds two small matrices A and B next to the original linear layer so that:
```
h = W₀x + BAx
```
in:
- W₀ is the frozen pre-trained weights
- B ∈ ℝᵈˣʳ, A ∈ ℝʳˣᵏ are trainable low-rank matrices
- r << min(d,k), greatly reducing the number of parameters

This design maintains the knowledge of the pre-trained model while efficiently adapting to new tasks.