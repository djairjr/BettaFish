# -*- coding: utf-8 -*-
"""XGBoost sentiment analysis model training script"""
import argparse
import pandas as pd
import numpy as np
from typing import List, Tuple
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
import xgboost as xgb

from base_model import BaseModel
from utils import stopwords


class XGBoostModel(BaseModel):
    """XGBoost sentiment analysis model"""
    
    def __init__(self):
        super().__init__("XGBoost")
        
    def train(self, train_data: List[Tuple[str, int]], **kwargs) -> None:
        """Train XGBoost model
        
        Args:
            train_data: training data in the format [(text, label), ...]
            **kwargs: other parameters, supporting various parameters of XGBoost"""
        print(f"Start training {self.model_name} model...")
        
        # Prepare data
        df_train = pd.DataFrame(train_data, columns=["words", "label"])
        
        # Feature encoding (bag-of-words model, limited number of features)
        max_features = kwargs.get('max_features', 2000)
        print(f"Build a bag-of-words model (max_features={max_features})...")
        self.vectorizer = CountVectorizer(
            token_pattern=r'\[?\w+\]?', 
            stop_words=stopwords,
            max_features=max_features
        )
        
        X_train = self.vectorizer.fit_transform(df_train["words"])
        y_train = df_train["label"]
        
        print(f"Feature dimension: {X_train.shape[1]}")
        
        # XGBoost parameter settings
        params = {
            'booster': kwargs.get('booster', 'gbtree'),
            'max_depth': kwargs.get('max_depth', 6),
            'scale_pos_weight': kwargs.get('scale_pos_weight', 0.5),
            'colsample_bytree': kwargs.get('colsample_bytree', 0.8),
            'objective': 'binary:logistic',
            'eval_metric': 'error',
            'eta': kwargs.get('eta', 0.3),
            'nthread': kwargs.get('nthread', 10),
        }
        
        num_boost_round = kwargs.get('num_boost_round', 200)
        
        print(f"Train XGBoost classifier...")
        print(f"Parameters: {params}")
        print(f"Number of iteration rounds: {num_boost_round}")
        
        # Create DMatrix
        dmatrix = xgb.DMatrix(X_train, label=y_train)
        
        # Training model
        self.model = xgb.train(params, dmatrix, num_boost_round=num_boost_round)
        
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
        
        # Create DMatrix
        dmatrix = xgb.DMatrix(X)
        
        # Predicted probability
        y_prob = self.model.predict(dmatrix)
        
        # Convert to category labels
        y_pred = (y_prob > 0.5).astype(int)
        
        return y_pred.tolist()
    
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
        
        # Create DMatrix
        dmatrix = xgb.DMatrix(X)
        
        # Predicted probability
        prob = self.model.predict(dmatrix)[0]
        
        # Convert to class labels and confidence
        prediction = int(prob > 0.5)
        confidence = prob if prediction == 1 else 1 - prob
        
        return prediction, float(confidence)
    
    def evaluate(self, test_data: List[Tuple[str, int]]) -> dict:
        """Evaluate model performance, including AUC indicator"""
        if not self.is_trained:
            raise ValueError(f"The model {self.model_name} has not been trained yet, please call the train method first")
            
        texts = [item[0] for item in test_data]
        labels = [item[1] for item in test_data]
        
        # Prediction category
        predictions = self.predict(texts)
        
        # Predicted probability (used to calculate AUC)
        X = self.vectorizer.transform(texts)
        dmatrix = xgb.DMatrix(X)
        probabilities = self.model.predict(dmatrix)
        
        accuracy = accuracy_score(labels, predictions)
        f1 = f1_score(labels, predictions, average='weighted')
        auc = roc_auc_score(labels, probabilities)
        
        print(f"\n{self.model_name} Model evaluation results:")
        print(f"Accuracy: {accuracy:.4f}")
        print(f"F1 score: {f1:.4f}")
        print(f"AUC: {auc:.4f}")
        
        return {
            'accuracy': accuracy,
            'f1_score': f1,
            'auc': auc
        }


def main():
    """main function"""
    parser = argparse.ArgumentParser(description='XGBoost情感分析模型训练')
    parser.add_argument('--train_path', type=str, default='./data/weibo2018/train.txt',
                        help='训练数据路径')
    parser.add_argument('--test_path', type=str, default='./data/weibo2018/test.txt',
                        help='测试数据路径')
    parser.add_argument('--model_path', type=str, default='./model/xgboost_model.pkl',
                        help='模型保存路径')
    parser.add_argument('--max_features', type=int, default=2000,
                        help='最大特征数量')
    parser.add_argument('--max_depth', type=int, default=6,
                        help='XGBoost最大深度')
    parser.add_argument('--eta', type=float, default=0.3,
                        help='XGBoost学习率')
    parser.add_argument('--num_boost_round', type=int, default=200,
                        help='XGBoost迭代轮数')
    parser.add_argument('--eval_only', action='store_true',
                        help='仅评估已有模型，不进行训练')
    
    args = parser.parse_args()
    
    # Create model
    model = XGBoostModel()
    
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
        model.train(
            train_data,
            max_features=args.max_features,
            max_depth=args.max_depth,
            eta=args.eta,
            num_boost_round=args.num_boost_round
        )
        
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