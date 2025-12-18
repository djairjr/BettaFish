# -*- coding: utf-8 -*-
"""Naive Bayes sentiment analysis model training script"""
import argparse
import pandas as pd
from typing import List, Tuple
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.metrics import accuracy_score, f1_score

from base_model import BaseModel
from utils import stopwords


class BayesModel(BaseModel):
    """Naive Bayes sentiment analysis model"""
    
    def __init__(self):
        super().__init__("Bayes")
        
    def train(self, train_data: List[Tuple[str, int]], **kwargs) -> None:
        """Train a Naive Bayes model
        
        Args:
            train_data: training data in the format [(text, label), ...]
            **kwargs: other parameters"""
        print(f"Start training {self.model_name} model...")
        
        # Prepare data
        df_train = pd.DataFrame(train_data, columns=["words", "label"])
        
        # Feature encoding (bag-of-words model)
        print("Build a bag-of-words model...")
        self.vectorizer = CountVectorizer(
            token_pattern=r'\[?\w+\]?', 
            stop_words=stopwords
        )
        
        X_train = self.vectorizer.fit_transform(df_train["words"])
        y_train = df_train["label"]
        
        print(f"Feature dimension: {X_train.shape[1]}")
        
        # Training model
        print("Training a Naive Bayes Classifier...")
        self.model = MultinomialNB()
        self.model.fit(X_train, y_train)
        
        self.is_trained = True
        print(f"{self.model_name} Model training completed!")
        
    def predict(self, texts: List[str]) -> List[int]:
        """Predict text sentiment
        
        Args:
            texts: list of texts to be predicted
            
        Returns:
            Prediction result list"""
        if not self.is_trained:
            raise ValueError(f"The model {self.model_name} has not been trained yet, please call the train method first")
            
        # Feature transformation
        X = self.vectorizer.transform(texts)
        
        # predict
        predictions = self.model.predict(X)
        
        return predictions.tolist()
    
    def predict_single(self, text: str) -> Tuple[int, float]:
        """Predicting the sentiment of a single text
        
        Args:
            text: text to be predicted
            
        Returns:
            (predicted_label, confidence)"""
        if not self.is_trained:
            raise ValueError(f"The model {self.model_name} has not been trained yet, please call the train method first")
            
        # Feature transformation
        X = self.vectorizer.transform([text])
        
        # predict
        prediction = self.model.predict(X)[0]
        probabilities = self.model.predict_proba(X)[0]
        confidence = max(probabilities)
        
        return int(prediction), float(confidence)


def main():
    """main function"""
    parser = argparse.ArgumentParser(description='朴素贝叶斯情感分析模型训练')
    parser.add_argument('--train_path', type=str, default='./data/weibo2018/train.txt',
                        help='训练数据路径')
    parser.add_argument('--test_path', type=str, default='./data/weibo2018/test.txt',
                        help='测试数据路径')
    parser.add_argument('--model_path', type=str, default='./model/bayes_model.pkl',
                        help='模型保存路径')
    parser.add_argument('--eval_only', action='store_true',
                        help='仅评估已有模型，不进行训练')
    
    args = parser.parse_args()
    
    # Create model
    model = BayesModel()
    
    if args.eval_only:
        # Evaluate mode only
        print("Evaluation mode: Load an existing model for evaluation")
        model.load_model(args.model_path)
        
        # Load test data
        _, test_data = BaseModel.load_data(args.train_path, args.test_path)
        
        # Evaluation model
        model.evaluate(test_data)
    else:
        # training mode
        # Load data
        train_data, test_data = BaseModel.load_data(args.train_path, args.test_path)
        
        # Training model
        model.train(train_data)
        
        # Evaluation model
        model.evaluate(test_data)
        
        # Save model
        model.save_model(args.model_path)
        
        # Example forecast
        print("\nExample prediction:")
        test_texts = [
            "The weather is so nice today, I feel great",
            "This movie is so boring and a waste of time",
            "Hahaha, so funny"
        ]
        
        for text in test_texts:
            pred, conf = model.predict_single(text)
            sentiment = "front" if pred == 1 else "Negative"
            print(f"Text: {text}")
            print(f"Prediction: {sentiment} (Confidence: {conf:.4f})")
            print()


if __name__ == "__main__":
    main()