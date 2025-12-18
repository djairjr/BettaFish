# Weibo emotion recognition model-GPT2-Adapter fine-tuning

## Project description
This is a Weibo emotion binary classification model based on GPT2, using Adapter fine-tuning technology. Through Adapter fine-tuning, only a small number of parameters need to be trained to adapt the model to sentiment analysis tasks, significantly reducing computing resource requirements and model volume.

## Dataset
The Weibo emotion data set (weibo_senti_100k) is used, which contains about 100,000 pieces of Weibo content with emotional annotations, and about 50,000 positive and negative comments each. Dataset labels:
- Tag 0: Negative emotions
- Tag 1: Positive emotions

## File structure
```
GPT2-Adpter-tuning/
├── adapter.py # Implementation of Adapter layer
├── gpt2_adapter.py # Adapter implementation for GPT2 model
├── train.py # training script
├── predict.py # Simplified version of prediction script (interactive use)
├── models/ # Locally stored pre-trained models
│ └── gpt2-chinese/ # Chinese GPT2 model and configuration
├── dataset/ # Dataset directory
│ └── weibo_senti_100k.csv # Weibo emotion data set
└── best_weibo_sentiment_model.pth # The best trained model
```

## Technical features

1. **Efficient parameter fine-tuning**: Compared with full-parameter fine-tuning, only about 3% of the parameters are trained.
2. **Model performance maintenance**: Maintain good classification performance when only training a small number of parameters
3. **Suitable for resource-constrained environments**: small model size and fast inference speed

## Environment dependencies
- Python 3.6+
- PyTorch
- Transformers
- Pandas
- NumPy
- Scikit-learn
- Tqdm

## How to use

### Training model
```bash
python train.py
```
The training process will automatically:
- Download and save the Chinese GPT2 pre-trained model locally
- Load Weibo emotion data set
- Train models and save the best models

### Sentiment Analysis Prediction
```bash
python predict.py
```
After running, you will enter interactive mode:
- Enter the Weibo text to be analyzed in the console
- The system returns sentiment analysis results (positive/negative) and confidence levels
- Enter 'q' to exit the program

## Model structure
- Basic model: `uer/gpt2-chinese-cluecorpussmall` Chinese pre-training model
- Local saving path of the model: `./models/gpt2-chinese/`
- Fine-tune by adding an Adapter layer after each GPT2Block
- Freeze original GPT2 parameters and only train classifier and Adapter layer parameters

## Adapter technology
Adapter is a parameter-efficient fine-tuning technology that inserts a small bottleneck layer into the Transformer layer to adapt to downstream tasks with a small number of parameters. Main features:

1. **Parameter Efficiency**: Compared with full parameter fine-tuning, the Adapter only needs to train a small part of the parameters.
2. **Prevent forgetting**: Keep the parameters of the original pre-trained model unchanged to avoid catastrophic forgetting
3. **Adapt to multi-tasking**: Different Adapters can be trained for different tasks and share the same basic model.

In this project, we added an Adapter layer after each GPT2Block. The hidden layer size of the Adapter is 64, which is much smaller than the hidden layer size of the original model (usually 768 or 1024).

## Usage example
```
Equipment used: cuda
Load model: best_weibo_sentiment_model.pth

============= Weibo Sentiment Analysis =============
Enter Weibo content for analysis (enter 'q' to exit):

Please enter Weibo content: This movie is so beautiful, I like it very much!
Prediction: Positive sentiment (Confidence: 0.9876)

Please enter Weibo content: Poor service attitude, expensive prices, not recommended at all
Prediction: Negative sentiment (Confidence: 0.9742)
```

## Notes
- The prediction script uses the local model path and does not require online downloading of the model.
- Make sure the `models/gpt2-chinese/` directory contains the model files saved from the training process
- The model will be automatically downloaded and saved when running train.py for the first time, please ensure the network connection