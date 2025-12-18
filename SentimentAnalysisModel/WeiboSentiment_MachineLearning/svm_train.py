# -*- coding: utf-8 -*-
"""SVM sentiment analysis model training script"""
import argparse
import pandas as pd
from typing import List, Tuple
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn import svm
from sklearn.metrics import accuracy_score, f1_score

from base_model import BaseModel
from utils import stopwords


class SVMModel(BaseModel):
    """SVM sentiment analysis model"""
    
    def __init__(self):
        super().__init__("SVM")
        
    def train(self, train_data: List[Tuple[str, int]], **kwargs) -> None:
        """Train SVM model
        
        Args:
            train_data: training data in the format [(text, label), ...]
            **kwargs: Other parameters, support kernel, C and other SVM parameters"""
        print(f"Start training {self.model_name} model...")
        
        # Prepare data
        df_train = pd.DataFrame(train_data, columns=["words", "label"])
        
        # Feature encoding (TF-IDF model)
        print("Construct TF-IDF features...")
        self.vectorizer = TfidfVectorizer(
            token_pattern=r'\[?\w+\]?', 
            stop_words=stopwords
        )
        
        X_train = self.vectorizer.fit_transform(df_train["words"])
        y_train = df_train["label"]
        
        print(f"Feature dimension: {X_train.shape[1]}")
        
        # Get SVM parameters
        kernel = kwargs.get('kernel', 'rbf')
        C = kwargs.get('C', 1.0)
        gamma = kwargs.get('gamma', 'scale')
        
        # Training model
        print(f"Train SVM classifier (kernel={kernel}, C={C}, gamma={gamma})...")
        self.model = svm.SVC(kernel=kernel, C=C, gamma=gamma, probability=True)
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
    parser = argparse.ArgumentParser(description='SVM情感分析模型训练')
    parser.add_argument('--train_path', type=str, default='./data/weibo2018/train.txt',
                        help='训练数据路径')
    parser.add_argument('--test_path', type=str, default='./data/weibo2018/test.txt',
                        help='测试数据路径')
    parser.add_argument('--model_path', type=str, default='./model/svm_model.pkl',
                        help='模型保存路径')
    parser.add_argument('--kernel', type=str, default='rbf', choices=['linear', 'poly', 'rbf', 'sigmoid'],
                        help='SVM核函数类型')
    parser.add_argument('--C', type=float, default=1.0,
                        help='SVM正则化参数C')
    parser.add_argument('--gamma', type=str, default='scale',
                        help='SVM核函数参数gamma')
    parser.add_argument('--eval_only', action='store_true',
                        help='仅评估已有模型，不进行训练')
    
    args = parser.parse_args()
    
    # Create model
    model = SVMModel()
    
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
        model.train(train_data, kernel=args.kernel, C=args.C, gamma=args.gamma)
        
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