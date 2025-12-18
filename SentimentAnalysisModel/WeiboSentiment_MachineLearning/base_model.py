# -*- coding: utf-8 -*-
"""Basic model class, providing a unified interface for all sentiment analysis models"""
import os
import pickle
from abc import ABC, abstractmethod
from typing import List, Tuple, Dict, Any
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score, classification_report
from utils import load_corpus


class BaseModel(ABC):
    """Sentiment analysis model base class"""
    
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.model = None
        self.vectorizer = None
        self.is_trained = False
        
    @abstractmethod
    def train(self, train_data: List[Tuple[str, int]], **kwargs) -> None:
        """Training model"""
        pass
    
    @abstractmethod
    def predict(self, texts: List[str]) -> List[int]:
        """Predict text sentiment"""
        pass
    
    def predict_single(self, text: str) -> Tuple[int, float]:
        """Predicting the sentiment of a single text
        
        Args:
            text: text to be predicted
            
        Returns:
            (predicted_label, confidence)"""
        predictions = self.predict([text])
        return predictions[0], 0.0  # The default confidence level is 0
    
    def evaluate(self, test_data: List[Tuple[str, int]]) -> Dict[str, float]:
        """Evaluate model performance"""
        if not self.is_trained:
            raise ValueError(f"The model {self.model_name} has not been trained yet, please call the train method first")
            
        texts = [item[0] for item in test_data]
        labels = [item[1] for item in test_data]
        
        predictions = self.predict(texts)
        
        accuracy = accuracy_score(labels, predictions)
        f1 = f1_score(labels, predictions, average='weighted')
        
        print(f"\n{self.model_name} Model evaluation results:")
        print(f"Accuracy: {accuracy:.4f}")
        print(f"F1 score: {f1:.4f}")
        print("\nDetailed report:")
        print(classification_report(labels, predictions))
        
        return {
            'accuracy': accuracy,
            'f1_score': f1,
            'classification_report': classification_report(labels, predictions)
        }
    
    def save_model(self, model_path: str = None) -> None:
        """Save model to file"""
        if not self.is_trained:
            raise ValueError(f"Model {self.model_name} has not been trained and cannot be saved.")
            
        if model_path is None:
            model_path = f"model/{self.model_name}_model.pkl"
            
        # Create save directory
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        
        # Save model data
        model_data = {
            'model': self.model,
            'vectorizer': self.vectorizer,
            'model_name': self.model_name,
            'is_trained': self.is_trained
        }
        
        with open(model_path, 'wb') as f:
            pickle.dump(model_data, f)
            
        print(f"Model saved to: {model_path}")
    
    def load_model(self, model_path: str) -> None:
        """Load model from file"""
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model file does not exist: {model_path}")
            
        with open(model_path, 'rb') as f:
            model_data = pickle.load(f)
            
        self.model = model_data['model']
        self.vectorizer = model_data.get('vectorizer')
        self.model_name = model_data['model_name']
        self.is_trained = model_data['is_trained']
        
        print(f"Loaded model: {model_path}")
    
    @staticmethod
    def load_data(train_path: str, test_path: str) -> Tuple[List[Tuple[str, int]], List[Tuple[str, int]]]:
        """Load training and test data"""
        print("Load training data...")
        train_data = load_corpus(train_path)
        print(f"Training data size: {len(train_data)}")
        
        print("Load test data...")
        test_data = load_corpus(test_path)
        print(f"Test data amount: {len(test_data)}")
        
        return train_data, test_data