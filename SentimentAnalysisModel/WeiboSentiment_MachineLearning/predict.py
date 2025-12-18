# -*- coding: utf-8 -*-
"""Unified Sentiment Analysis Prediction Program
Support loading all models for sentiment prediction"""
import argparse
import os
import re
from typing import Dict, Tuple, List
import warnings
warnings.filterwarnings("ignore")

# Import all model classes
from bayes_train import BayesModel
from svm_train import SVMModel
from xgboost_train import XGBoostModel
from lstm_train import LSTMModel
from bert_train import BertModel_Custom
from utils import processing


class SentimentPredictor:
    """Sentiment Analysis Predictor"""
    
    def __init__(self):
        self.models = {}
        self.available_models = {
            'bayes': BayesModel,
            'svm': SVMModel,
            'xgboost': XGBoostModel,
            'lstm': LSTMModel,
            'bert': BertModel_Custom
        }
        
    def load_model(self, model_type: str, model_path: str, **kwargs) -> None:
        """Load a model of a specified type
        
        Args:
            model_type: model type ('bayes', 'svm', 'xgboost', 'lstm', 'bert')
            model_path: model file path
            **kwargs: other parameters (such as BERT’s pre-training model path)"""
        if model_type not in self.available_models:
            raise ValueError(f"Unsupported model type: {model_type}")
        
        if not os.path.exists(model_path):
            print(f"Warning: Model file does not exist: {model_path}")
            return
        
        print(f"Loading {model_type.upper()} model...")
        
        try:
            if model_type == 'bert':
                # BERT requires additional pre-trained model paths
                bert_path = kwargs.get('bert_path', './model/chinese_wwm_pytorch')
                model = BertModel_Custom(bert_path)
            else:
                model = self.available_models[model_type]()
            
            model.load_model(model_path)
            self.models[model_type] = model
            print(f"{model_type.upper()} Model loaded successfully")
            
        except Exception as e:
            print(f"Failed to load model {model_type.upper()}: {e}")
    
    def load_all_models(self, model_dir: str = './model', bert_path: str = './model/chinese_wwm_pytorch') -> None:
        """Load all available models
        
        Args:
            model_dir: model file directory
            bert_path: BERT pre-training model path"""
        model_files = {
            'bayes': os.path.join(model_dir, 'bayes_model.pkl'),
            'svm': os.path.join(model_dir, 'svm_model.pkl'),
            'xgboost': os.path.join(model_dir, 'xgboost_model.pkl'),
            'lstm': os.path.join(model_dir, 'lstm_model.pth'),
            'bert': os.path.join(model_dir, 'bert_model.pth')
        }
        
        print("Start loading all available models...")
        for model_type, model_path in model_files.items():
            self.load_model(model_type, model_path, bert_path=bert_path)
        
        print(f"\n{len(self.models)} models have been loaded: {list(self.models.keys())}")
    
    def predict_single(self, text: str, model_type: str = None) -> Dict[str, Tuple[int, float]]:
        """Predicting the sentiment of a single text
        
        Args:
            text: text to be predicted
            model_type: Specifies the model type. If it is None, all loaded models will be used.
            
        Returns:
            Dict[model_type, (prediction, confidence)]"""
        # Text preprocessing
        processed_text = processing(text)
        
        if model_type:
            if model_type not in self.models:
                raise ValueError(f"Model {model_type} not loaded")
            
            prediction, confidence = self.models[model_type].predict_single(processed_text)
            return {model_type: (prediction, confidence)}
        
        # Predict using all models
        results = {}
        for name, model in self.models.items():
            try:
                prediction, confidence = model.predict_single(processed_text)
                results[name] = (prediction, confidence)
            except Exception as e:
                print(f"Model {name} failed to predict: {e}")
                results[name] = (0, 0.0)
        
        return results
    
    def predict_batch(self, texts: List[str], model_type: str = None) -> Dict[str, List[int]]:
        """Predicting text sentiment in batches
        
        Args:
            texts: list of texts to be predicted
            model_type: Specifies the model type. If it is None, all loaded models will be used.
            
        Returns:
            Dict[model_type, predictions]"""
        # Text preprocessing
        processed_texts = [processing(text) for text in texts]
        
        if model_type:
            if model_type not in self.models:
                raise ValueError(f"Model {model_type} not loaded")
            
            predictions = self.models[model_type].predict(processed_texts)
            return {model_type: predictions}
        
        # Predict using all models
        results = {}
        for name, model in self.models.items():
            try:
                predictions = model.predict(processed_texts)
                results[name] = predictions
            except Exception as e:
                print(f"Model {name} failed to predict: {e}")
                results[name] = [0] * len(texts)
        
        return results
    
    def ensemble_predict(self, text: str, weights: Dict[str, float] = None) -> Tuple[int, float]:
        """Ensemble prediction (multiple model voting)
        
        Args:
            text: text to be predicted
            weights: model weights, if None, the average weight
            
        Returns:
            (prediction, confidence)"""
        if len(self.models) == 0:
            raise ValueError("No models loaded")
        
        results = self.predict_single(text)
        
        if weights is None:
            weights = {name: 1.0 for name in results.keys()}
        
        # weighted average
        total_weight = 0
        weighted_prob = 0
        
        for model_name, (pred, conf) in results.items():
            if model_name in weights:
                weight = weights[model_name]
                prob = conf if pred == 1 else 1 - conf
                weighted_prob += prob * weight
                total_weight += weight
        
        if total_weight == 0:
            return 0, 0.5
        
        final_prob = weighted_prob / total_weight
        final_pred = int(final_prob > 0.5)
        final_conf = final_prob if final_pred == 1 else 1 - final_prob
        
        return final_pred, final_conf
    
    def interactive_predict(self):
        """Interactive prediction mode"""
        if len(self.models) == 0:
            print("Error: No model loaded, please load the model first")
            return
        
        print("\n" + "="*50)
        print("="*50)
        print(f"Loaded model: {', '.join(self.models.keys())}")
        print("Type 'q' to exit the program")
        print("Type 'models' to see a list of models")
        print("Enter 'ensemble' to use ensemble prediction")
        print("-"*50)
        
        while True:
            try:
                text = input("\nPlease enter the Weibo content to be analyzed:").strip()
                
                if text.lower() == 'q':
                    print("👋 Goodbye!")
                    break
                
                if text.lower() == 'models':
                    print(f"Loaded models: {list(self.models.keys())}")
                    continue
                
                if text.lower() == 'ensemble':
                    if len(self.models) > 1:
                        pred, conf = self.ensemble_predict(text)
                        sentiment = "😊 Positive" if pred == 1 else "😞 Negative"
                        print(f"\n🤖 Integrated prediction results:")
                        print(f"Sentiment: {sentiment}")
                        print(f"Confidence: {conf:.4f}")
                    else:
                        print("❌ Ensemble prediction requires at least 2 models")
                    continue
                
                if not text:
                    print("❌ Please enter valid content")
                    continue
                
                # predict
                results = self.predict_single(text)
                
                print(f"\n📝 Original text: {text}")
                print("🔍 Prediction results:")
                
                for model_name, (pred, conf) in results.items():
                    sentiment = "😊 Positive" if pred == 1 else "😞 Negative"
                    print(f"{model_name.upper():8}: {sentiment} (confidence: {conf:.4f})")
                
                # If there are multiple models, display the integration results
                if len(results) > 1:
                    ensemble_pred, ensemble_conf = self.ensemble_predict(text)
                    ensemble_sentiment = "😊 Positive" if ensemble_pred == 1 else "😞 Negative"
                    print(f"{'ensemble':8}: {ensemble_sentiment} (Confidence: {ensemble_conf:.4f})")
                
            except KeyboardInterrupt:
                print("\n\n👋 The program was interrupted, goodbye!")
                break
            except Exception as e:
                print(f"❌ An error occurred during prediction: {e}")


def main():
    """main function"""
    parser = argparse.ArgumentParser(description='微博情感分析统一预测程序')
    parser.add_argument('--model_dir', type=str, default='./model',
                        help='模型文件目录')
    parser.add_argument('--bert_path', type=str, default='./model/chinese_wwm_pytorch',
                        help='BERT预训练模型路径')
    parser.add_argument('--model_type', type=str, choices=['bayes', 'svm', 'xgboost', 'lstm', 'bert'],
                        help='指定单个模型类型进行预测')
    parser.add_argument('--text', type=str,
                        help='直接预测指定文本')
    parser.add_argument('--interactive', action='store_true', default=True,
                        help='交互式预测模式（默认）')
    parser.add_argument('--ensemble', action='store_true',
                        help='使用集成预测')
    
    args = parser.parse_args()
    
    # Create predictor
    predictor = SentimentPredictor()
    
    # Load model
    if args.model_type:
        # Load the specified model
        model_files = {
            'bayes': 'bayes_model.pkl',
            'svm': 'svm_model.pkl',
            'xgboost': 'xgboost_model.pkl',
            'lstm': 'lstm_model.pth',
            'bert': 'bert_model.pth'
        }
        model_path = os.path.join(args.model_dir, model_files[args.model_type])
        predictor.load_model(args.model_type, model_path, bert_path=args.bert_path)
    else:
        # Load all models
        predictor.load_all_models(args.model_dir, args.bert_path)
    
    # If text is specified, predict directly
    if args.text:
        if args.ensemble and len(predictor.models) > 1:
            pred, conf = predictor.ensemble_predict(args.text)
            sentiment = "front" if pred == 1 else "Negative"
            print(f"Text: {args.text}")
            print(f"Ensemble prediction: {sentiment} (Confidence: {conf:.4f})")
        else:
            results = predictor.predict_single(args.text, args.model_type)
            print(f"Text: {args.text}")
            for model_name, (pred, conf) in results.items():
                sentiment = "front" if pred == 1 else "Negative"
                print(f"{model_name.upper()}: {sentiment} (Confidence: {conf:.4f})")
    elif args.interactive:
        # interactive mode
        predictor.interactive_predict()


if __name__ == "__main__":
    main()