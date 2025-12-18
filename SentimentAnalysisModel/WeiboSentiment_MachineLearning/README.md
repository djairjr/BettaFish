# Weibo Sentiment Analysis - Traditional Machine Learning Method

## Project introduction

This project uses 5 traditional machine learning methods to classify Chinese Weibo sentiment into two categories (positive/negative):

- **Naive Bayes**: Probabilistic classification based on bag-of-words model
- **SVM**: Support vector machine based on TF-IDF features
- **XGBoost**: Gradient boosting decision tree
- **LSTM**: Recurrent Neural Network + Word2Vec word vector
- **BERT+Classification Head**: Pre-trained language model connected to classifier (I think it also belongs to the traditional ML category)

## Model performance

Performance on Weibo emotion data set (training set 10,000 items, test set 500 items):

| Model | Accuracy | AUC | Features |
|------|--------|-----|------|
| Naive Bayes | 85.6% | - | Fast, small memory footprint |
| SVM | 85.6% | - | Good generalization ability |
| XGBoost | 86.0% | 90.4% | Stable performance, supporting feature importance |
| LSTM | 87.0% | 93.1% | Understand sequence information and context |
| BERT+ classification head | 87.0% | 92.9% | Powerful semantic understanding capabilities |

## Environment configuration

```bash
pip install -r requirements.txt
```

Data file structure:
```
data/
├── weibo2018/
│   ├── train.txt
│   └── test.txt
└── stopwords.txt
```

## Train the model (you can run it directly without parameters later)

### Naive Bayes
```bash
python bayes_train.py
```

### SVM
```bash
python svm_train.py --kernel rbf --C 1.0
```

### XGBoost
```bash
python xgboost_train.py --max_depth 6 --eta 0.3 --num_boost_round 200
```

### LSTM
```bash
python lstm_train.py --epochs 5 --batch_size 100 --hidden_size 64
```

### BERT
```bash
python bert_train.py --epochs 10 --batch_size 100 --learning_rate 1e-3
```

Note: The BERT model will automatically download the Chinese pre-training model (bert-base-chinese)

## Use predictions

### Interactive prediction (recommended)
```bash
python predict.py
```

### Command line prediction
```bash
#Single model prediction
python predict.py --model_type bert --text "The weather is really nice today and I am in a great mood"

#Multi-model ensemble prediction
python predict.py --ensemble --text "This movie is so boring"
```

## File structure

```
WeiboSentiment_MachineLearning/
├── bayes_train.py # Naive Bayes training
├── svm_train.py # SVM training
├── xgboost_train.py # XGBoost training
├── lstm_train.py # LSTM training
├── bert_train.py # BERT training
├── predict.py # Unified prediction program
├── base_model.py #Basic model class
├── utils.py # Utility function
├── requirements.txt # Dependency package
├── model/ # Model saving directory
└── data/ # Data directory
```

## Notes

1. The first run of **BERT model** will automatically download the pre-trained model (about 400MB)
2. **LSTM model** takes a long time to train, so it is recommended to use GPU
3. **Save the model** in the `model/` directory, make sure there is enough disk space
4. **Memory Requirements**BERT > LSTM > XGBoost > SVM > Naive Bayes
