#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Qwen3 Weibo Sentiment Analysis Unified Prediction Interface
Supports Embedding and LoRA models in three specifications: 0.6B, 4B, and 8B"""

import os
import sys
import argparse
import torch
from typing import List, Dict, Tuple, Any

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from models_config import QWEN3_MODELS, MODEL_PATHS
from qwen3_embedding_universal import Qwen3EmbeddingUniversal
from qwen3_lora_universal import Qwen3LoRAUniversal


class Qwen3UniversalPredictor:
    """Qwen3 unified predictor"""
    
    def __init__(self):
        self.models = {}  # Store the loaded model {model_key: {model: obj, display_name: str}}
        
    def _get_model_key(self, model_type: str, model_size: str) -> str:
        """Generate model key values"""
        return f"{model_type}_{model_size}"
    
    def load_model(self, model_type: str, model_size: str) -> None:
        """Load the specified model"""
        if model_type not in ['embedding', 'lora']:
            raise ValueError(f"Unsupported model type: {model_type}")
        if model_size not in ['0.6B', '4B', '8B']:
            raise ValueError(f"Unsupported model size: {model_size}")
            
        model_path = MODEL_PATHS[model_type][model_size]
        model_key = self._get_model_key(model_type, model_size)
        
        # Check whether the trained model file exists
        if not os.path.exists(model_path):
            print(f"The trained model file does not exist: {model_path}")
            print(f"Please train the {model_type.upper()}-{model_size} model first, or check the model path configuration")
            return
        
        print(f"加载 {model_type.upper()}-{model_size} 模型...")
        
        try:
            if model_type == 'embedding':
                model = Qwen3EmbeddingUniversal(model_size)
                model.load_model(model_path)
            else:  # lora
                model = Qwen3LoRAUniversal(model_size)
                model.load_model(model_path)
            
            self.models[model_key] = {
                'model': model,
                'display_name': f"Qwen3-{model_type.title()}-{model_size}"
            }
            print(f"{model_type.upper()}-{model_size} Model loaded successfully")
            
        except Exception as e:
            print(f"Failed to load {model_type.upper()}-{model_size} model: {e}")
            print(f"This may be because the base model download failed or the trained model file is damaged.")
    
    def load_all_models(self, model_dir: str = './models') -> None:
        """Load all available models"""
        print("Start loading all available Qwen3 models...")
        
        loaded_count = 0
        for model_type in ['embedding', 'lora']:
            for model_size in ['0.6B', '4B', '8B']:
                try:
                    self.load_model(model_type, model_size)
                    loaded_count += 1
                except Exception as e:
                    print(f"Skip {model_type}-{model_size}: {e}")
        
        print(f"\n{loaded_count} models loaded")
        self._print_loaded_models()
    
    def load_specific_models(self, model_configs: List[Tuple[str, str]]) -> None:
        """Load the specified model configuration
        Args:
            model_configs: list of [(model_type, model_size), ...]"""
        print("Load the specified Qwen3 model...")
        
        for model_type, model_size in model_configs:
            try:
                self.load_model(model_type, model_size)
            except Exception as e:
                print(f"Skip {model_type}-{model_size}: {e}")
        
        print(f"\n{len(self.models)} models loaded")
        self._print_loaded_models()
    
    def _print_loaded_models(self):
        """Print a list of loaded models"""
        if self.models:
            print("Loaded model:")
            for model_info in self.models.values():
                print(f"  - {model_info['display_name']}")
        else:
            print("No models were loaded successfully")
    
    def predict_single(self, text: str, model_key: str = None) -> Dict[str, Tuple[int, float]]:
        """single text prediction
        Args:
            text: text to predict
            model_key: Specify the model key value, None means use all models
        Returns:
            {model_name: (prediction, confidence), ...}"""
        results = {}
        
        if model_key and model_key in self.models:
            # Use specified model
            model_info = self.models[model_key]
            try:
                prediction, confidence = model_info['model'].predict_single(text)
                results[model_info['display_name']] = (prediction, confidence)
            except Exception as e:
                print(f"Model {model_info['display_name']} failed to predict: {e}")
                results[model_info['display_name']] = (0, 0.0)
        else:
            # Use all models
            for model_info in self.models.values():
                try:
                    prediction, confidence = model_info['model'].predict_single(text)
                    results[model_info['display_name']] = (prediction, confidence)
                except Exception as e:
                    print(f"Model {model_info['display_name']} failed to predict: {e}")
                    results[model_info['display_name']] = (0, 0.0)
        
        return results
    
    def predict_batch(self, texts: List[str]) -> Dict[str, List[int]]:
        """Batch prediction"""
        results = {}
        
        for model_info in self.models.values():
            try:
                predictions = model_info['model'].predict(texts)
                results[model_info['display_name']] = predictions
            except Exception as e:
                print(f"Model {model_info['display_name']} failed to predict: {e}")
                results[model_info['display_name']] = [0] * len(texts)
        
        return results
    
    def ensemble_predict(self, text: str) -> Tuple[int, float]:
        """Ensemble prediction"""
        if len(self.models) < 2:
            raise ValueError("Ensemble prediction requires at least 2 models")
        
        results = self.predict_single(text)
        
        # Weighted average (simple average is used here, and the weights can be adjusted according to model performance)
        total_weight = 0
        weighted_prob = 0
        
        for model_name, (pred, conf) in results.items():
            if conf > 0:  # Only valid predictions are considered
                prob = conf if pred == 1 else 1 - conf
                weighted_prob += prob
                total_weight += 1
        
        if total_weight == 0:
            return 0, 0.5
        
        final_prob = weighted_prob / total_weight
        final_pred = int(final_prob > 0.5)
        final_conf = final_prob if final_pred == 1 else 1 - final_prob
        
        return final_pred, final_conf
    
    def _select_and_load_model(self):
        """Let the user select and load a model"""
        print("Qwen3 Weibo sentiment analysis and prediction system")
        print("="*40)
        print("Please select the model to use:")
        print("\nMethod selection:")
        print("1. Embedding + classification header (fast inference, less memory usage)")
        print("2. LoRA fine-tuning (better effect, takes up more video memory)")
        
        method_choice = None
        while method_choice not in ['1', '2']:
            method_choice = input("\nPlease select a method (1/2):").strip()
            if method_choice not in ['1', '2']:
                print("Invalid selection, please enter 1 or 2")
        
        method_type = "embedding" if method_choice == '1' else "lora"
        method_name = "Embedding + classification header" if method_choice == '1' else "LoRA fine-tuning"
        
        print(f"\nSelected: {method_name}")
        print("\nModel size selection:")
        print("1. 0.6B - Lightweight, fast inference")
        print("2. 4B - Medium size, balanced performance") 
        print("3. 8B - Large scale, best performance")
        
        size_choice = None
        while size_choice not in ['1', '2', '3']:
            size_choice = input("\nPlease select model size (1/2/3):").strip()
            if size_choice not in ['1', '2', '3']:
                print("Invalid selection, please enter 1, 2 or 3")
        
        size_map = {'1': '0.6B', '2': '4B', '3': '8B'}
        model_size = size_map[size_choice]
        
        print(f"Selected: Qwen3-{method_name}-{model_size}")
        print("Loading model...")
        
        try:
            self.load_model(method_type, model_size)
            print(f"Model loaded successfully!")
        except Exception as e:
            print(f"Model loading failed: {e}")
            print("Please check if the model file exists, or train first")
    
    def interactive_predict(self):
        """Interactive prediction mode"""
        if len(self.models) == 0:
            # Let the user select which model to load
            self._select_and_load_model()
            if len(self.models) == 0:
                print("No model is loaded, exit prediction")
                return
        
        print("\n" + "="*60)
        print("Qwen3 Weibo sentiment analysis and prediction system")
        print("="*60)
        print("Loaded model:")
        for model_info in self.models.values():
            print(f"   - {model_info['display_name']}")
        print("\nCommand prompt:")
        print("Type 'q' to exit the program")
        print("Type 'switch' to switch models")  
        print("Type 'models' to view loaded models")
        print("Type 'compare' to compare all model performance")
        print("-"*60)
        
        while True:
            try:
                text = input("\nPlease enter the Weibo content to be analyzed:").strip()
                
                if text.lower() == 'q':
                    print("Thanks for using, bye!")
                    break
                
                if text.lower() == 'models':
                    print("Loaded model:")
                    for model_info in self.models.values():
                        print(f"   - {model_info['display_name']}")
                    continue
                
                if text.lower() == 'switch':
                    print("Switch model...")
                    self.models.clear()  # Clear current model
                    self._select_and_load_model()
                    if len(self.models) > 0:
                        print("Model switching successful!")
                        for model_info in self.models.values():
                            print(f"Current model: {model_info['display_name']}")
                    continue
                
                if text.lower() == 'compare':
                    test_text = input("Please enter the text to compare:")
                    self._compare_models(test_text)
                    continue
                
                if not text:
                    print("Please enter valid content")
                    continue
                
                # predict
                results = self.predict_single(text)
                
                print(f"\nOriginal text: {text}")
                print("Predicted results:")
                
                # Display sorted by model type and size
                sorted_results = sorted(results.items())
                for model_name, (pred, conf) in sorted_results:
                    sentiment = "front" if pred == 1 else "Negative"
                    print(f"{model_name:20}: {sentiment} (Confidence: {conf:.4f})")
                
                # Only display the prediction results of a single model (no integration)
                
            except KeyboardInterrupt:
                print("\n\nThe program was interrupted, goodbye!")
                break
            except Exception as e:
                print(f"An error occurred during prediction: {e}")
    
    def _compare_models(self, text: str):
        """Compare the performance of different models"""
        print(f"\nModel performance comparison - text: {text}")
        print("-" * 60)
        
        results = self.predict_single(text)
        
        embedding_models = []
        lora_models = []
        
        for model_name, (pred, conf) in results.items():
            sentiment = "front" if pred == 1 else "Negative"
            if "Embedding" in model_name:
                embedding_models.append((model_name, sentiment, conf))
            elif "Lora" in model_name:
                lora_models.append((model_name, sentiment, conf))
        
        if embedding_models:
            print("Embedding + classification header method:")
            for name, sentiment, conf in embedding_models:
                print(f"   {name}: {sentiment} ({conf:.4f})")
        
        if lora_models:
            print("LoRA fine-tuning method:")
            for name, sentiment, conf in lora_models:
                print(f"   {name}: {sentiment} ({conf:.4f})")


def main():
    """main function"""
    parser = argparse.ArgumentParser(description='Qwen3微博情感分析统一预测接口')
    parser.add_argument('--model_dir', type=str, default='./models',
                        help='模型文件目录')
    parser.add_argument('--model_type', type=str, choices=['embedding', 'lora'],
                        help='指定模型类型')
    parser.add_argument('--model_size', type=str, choices=['0.6B', '4B', '8B'],
                        help='指定模型大小')
    parser.add_argument('--text', type=str,
                        help='直接预测指定文本')
    parser.add_argument('--interactive', action='store_true', default=True,
                        help='交互式预测模式（默认）')
    parser.add_argument('--ensemble', action='store_true',
                        help='使用集成预测')
    parser.add_argument('--load_all', action='store_true',
                        help='加载所有可用模型')
    
    args = parser.parse_args()
    
    # Create predictor
    predictor = Qwen3UniversalPredictor()
    
    # Load model
    if args.load_all:
        # Load all models
        predictor.load_all_models(args.model_dir)
    elif args.model_type and args.model_size:
        # Load the specified model
        predictor.load_model(args.model_type, args.model_size)
    # If no model is specified, interactive mode lets the user choose
    
    # If text is specified, predict directly
    if args.text:
        if args.ensemble and len(predictor.models) > 1:
            pred, conf = predictor.ensemble_predict(args.text)
            sentiment = "front" if pred == 1 else "Negative"
            print(f"Text: {args.text}")
            print(f"Ensemble prediction: {sentiment} (Confidence: {conf:.4f})")
        else:
            results = predictor.predict_single(args.text)
            print(f"Text: {args.text}")
            for model_name, (pred, conf) in results.items():
                sentiment = "front" if pred == 1 else "Negative"
                print(f"{model_name}: {sentiment} (Confidence: {conf:.4f})")
    else:
        # Enter interactive mode
        predictor.interactive_predict()


if __name__ == "__main__":
    main()