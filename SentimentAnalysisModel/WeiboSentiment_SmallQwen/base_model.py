# -*- coding: utf-8 -*-
"""Qwen3 model basic class, unified interface"""
import os
import pickle
from abc import ABC, abstractmethod
from typing import List, Tuple, Dict, Any
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score, classification_report
from sklearn.model_selection import train_test_split


class BaseQwenModel(ABC):
    """Qwen3 sentiment analysis model base class"""
    
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.model = None
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
    
    @abstractmethod
    def save_model(self, model_path: str = None) -> None:
        """Save model to file"""
        pass
    
    @abstractmethod
    def load_model(self, model_path: str) -> None:
        """Load model from file"""
        pass
    
    @staticmethod
    def load_data(train_path: str = None, test_path: str = None, csv_path: str = 'dataset/weibo_senti_100k.csv') -> Tuple[List[Tuple[str, int]], List[Tuple[str, int]]]:
        """Load training and test data
        
        Args:
            train_path: training data txt file path (optional)
            test_path: test data txt file path (optional)
            csv_path: CSV data file path (used by default)"""
        
        # Try using CSV files first
        if os.path.exists(csv_path):
            print(f"Load data from CSV file: {csv_path}")
            df = pd.read_csv(csv_path)
            
            # Check data format
            if 'review' in df.columns and 'label' in df.columns:
                # Convert DataFrame to list of tuples
                data = [(row['review'], row['label']) for _, row in df.iterrows()]
                
                # Split training and test data, with a fixed test set of 5,000 records
                total_samples = len(data)
                if total_samples > 5000:
                    test_size = 5000
                    train_data, test_data = train_test_split(
                        data, 
                        test_size=test_size, 
                        random_state=42, 
                        stratify=[label for _, label in data]
                    )
                else:
                    # If the total data is less than 5,000, use 20% as the test set
                    train_data, test_data = train_test_split(
                        data, 
                        test_size=0.2, 
                        random_state=42, 
                        stratify=[label for _, label in data]
                    )
                
                print(f"Training data size: {len(train_data)}")
                print(f"Test data amount: {len(test_data)}")
                
                return train_data, test_data
            else:
                print(f"CSV file is malformed, missing 'review' or 'label' column")
        
        # If the CSV does not exist, try using a txt file
        elif train_path and test_path and os.path.exists(train_path) and os.path.exists(test_path):
            def load_corpus(path):
                data = []
                with open(path, "r", encoding="utf8") as f:
                    for line in f:
                        parts = line.strip().split("\t")
                        if len(parts) >= 2:
                            content = parts[0]
                            sentiment = int(parts[1])
                            data.append((content, sentiment))
                return data
            
            print("Load training data from txt file...")
            train_data = load_corpus(train_path)
            print(f"Training data size: {len(train_data)}")
            
            print("Load test data from txt file...")
            test_data = load_corpus(test_path)
            print(f"Test data amount: {len(test_data)}")
            
            return train_data, test_data
        
        else:
            # If none, provide sample data creation guidance.
            print("Data file not found!")
            print("Please make sure one of the following files exists:")
            print(f"1. CSV file: {csv_path}")
            print(f"2. txt file: {train_path} and {test_path}")
            print("\nData format requirements:")
            print("CSV file: Contains 'review' and 'label' columns")
            print("txt file: The format of each line is 'text content\\t label'")
            
            # Create sample data
            sample_data = [
                ("The weather is so nice today and I’m in a great mood!", 1),
                ("This movie is so boring", 0),
                ("Like this product very much", 1),
                ("Very poor service attitude", 0),
                ("Good quality, worth recommending", 1)
            ]
            
            print("Demonstration using sample data...")
            train_data = sample_data * 20  # Extend sample data
            test_data = sample_data * 5
            
            return train_data, test_data