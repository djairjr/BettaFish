# -*- coding: utf-8 -*-
"""Qwen3-LoRA general training script
Supports models of three sizes: 0.6B, 4B, and 8B"""
import argparse
import os
import torch
from transformers import (
    AutoTokenizer, 
    AutoModelForCausalLM, 
    TrainingArguments, 
    Trainer,
    DataCollatorForLanguageModeling
)
from peft import LoraConfig, get_peft_model, TaskType, PeftModel
from datasets import Dataset
from typing import List, Tuple
import warnings
from tqdm import tqdm

from base_model import BaseQwenModel
from models_config import QWEN3_MODELS, MODEL_PATHS

warnings.filterwarnings("ignore")


class Qwen3LoRAUniversal(BaseQwenModel):
    """Universal Qwen3-LoRA model"""
    
    def __init__(self, model_size: str = "0.6B"):
        if model_size not in QWEN3_MODELS:
            raise ValueError(f"Unsupported model size: {model_size}")
            
        super().__init__(f"Qwen3-{model_size}-LoRA")
        self.model_size = model_size
        self.config = QWEN3_MODELS[model_size]
        self.model_name_hf = self.config["base_model"]
        
        self.tokenizer = None
        self.base_model = None
        self.lora_model = None
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
    def _load_base_model(self):
        """Load Qwen3 basic model"""
        print(f"Load {self.model_size} basic model: {self.model_name_hf}")
        
        # Step 1: Check the models directory of the current folder
        local_model_dir = f"./models/qwen3-{self.model_size.lower()}"
        if os.path.exists(local_model_dir) and os.path.exists(os.path.join(local_model_dir, "config.json")):
            try:
                print(f"Discover the local model and load it from local: {local_model_dir}")
                self.tokenizer = AutoTokenizer.from_pretrained(local_model_dir)
                self.base_model = AutoModelForCausalLM.from_pretrained(
                    local_model_dir,
                    torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                    device_map="auto" if torch.cuda.is_available() else None
                )
                
                # Set pad_token
                if self.tokenizer.pad_token is None:
                    self.tokenizer.pad_token = self.tokenizer.eos_token
                    self.tokenizer.pad_token_id = self.tokenizer.eos_token_id
                
                print(f"Loading {self.model_size} basic model from local model successfully")
                return
                
            except Exception as e:
                print(f"Local model loading failed: {e}")
        
        # Step Two: Check HuggingFace Cache
        try:
            from transformers.utils import default_cache_path
            cache_path = default_cache_path
            print(f"Check HuggingFace cache: {cache_path}")
            
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name_hf)
            self.base_model = AutoModelForCausalLM.from_pretrained(
                self.model_name_hf,
                torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                device_map="auto" if torch.cuda.is_available() else None
            )
            
            # Set pad_token
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token
                self.tokenizer.pad_token_id = self.tokenizer.eos_token_id
            
            print(f"Loading {self.model_size} basic model from HuggingFace cache successfully")
            
            # Save to local models directory
            print(f"Save the model to local: {local_model_dir}")
            os.makedirs(local_model_dir, exist_ok=True)
            self.tokenizer.save_pretrained(local_model_dir)
            self.base_model.save_pretrained(local_model_dir)
            print(f"Model saved to: {local_model_dir}")
            
        except Exception as e:
            print(f"Loading from HuggingFace cache failed: {e}")
            
            # Step 3: Download from HuggingFace
            try:
                print(f"Downloading {self.model_size} model from HuggingFace...")
                
                self.tokenizer = AutoTokenizer.from_pretrained(
                    self.model_name_hf,
                    force_download=True
                )
                self.base_model = AutoModelForCausalLM.from_pretrained(
                    self.model_name_hf,
                    force_download=True,
                    torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                    device_map="auto" if torch.cuda.is_available() else None
                )
                
                if self.tokenizer.pad_token is None:
                    self.tokenizer.pad_token = self.tokenizer.eos_token
                    self.tokenizer.pad_token_id = self.tokenizer.eos_token_id
                
                # Save to local models directory
                os.makedirs(local_model_dir, exist_ok=True)
                self.tokenizer.save_pretrained(local_model_dir)
                self.base_model.save_pretrained(local_model_dir)
                print(f"{self.model_size} model is downloaded and saved to: {local_model_dir}")
                
            except Exception as e2:
                print(f"Downloading from HuggingFace also failed: {e2}")
                raise RuntimeError(f"Unable to load {self.model_size} model, all methods failed")
    
    def _create_instruction_data(self, data: List[Tuple[str, int]]) -> Dataset:
        """Create training data in command format"""
        instructions = []
        
        for text, label in data:
            sentiment = "front" if label == 1 else "Negative"
            
            # Build command format
            instruction = f"Please analyze the emotional tendency of the following Weibo text and answer 'positive' or 'negative'. \n\nText: {text}\n\nEmotion:"
            response = sentiment
            
            
            # Combined into complete training text
            full_text = f"{instruction}{response}{self.tokenizer.eos_token}"
            
            instructions.append({
                "instruction": instruction,
                "response": response,
                "text": full_text
            })
        
        return Dataset.from_list(instructions)
    
    def _tokenize_function(self, examples):
        """word segmentation function"""
        tokenized = self.tokenizer(
            examples["text"],
            truncation=True,
            padding="max_length",
            max_length=512,
            return_tensors=None
        )
        
        tokenized["labels"] = tokenized["input_ids"].copy()
        return tokenized
    
    def _setup_lora(self, **kwargs):
        """Set LoRA configuration"""
        lora_r = kwargs.get('lora_r', self.config['lora_r'])
        lora_alpha = kwargs.get('lora_alpha', self.config['lora_alpha'])
        
        lora_config = LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            r=lora_r,
            lora_alpha=lora_alpha,
            lora_dropout=kwargs.get('lora_dropout', 0.1),
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        )
        
        self.lora_model = get_peft_model(self.base_model, lora_config)
        
        # Statistical parameters
        total_params = sum(p.numel() for p in self.lora_model.parameters())
        trainable_params = sum(p.numel() for p in self.lora_model.parameters() if p.requires_grad)
        
        print(f"LoRA configuration completed (r={lora_r}, alpha={lora_alpha})")
        print(f"Total parameters: {total_params:,}")
        print(f"Trainable parameters: {trainable_params:,}")
        print(f"Trainable parameter ratio: {trainable_params / total_params * 100:.2f}%")
        self.lora_model.print_trainable_parameters()  # Parameter statistics that come with the PEFT library
        
        return lora_config
    
    def train(self, train_data: List[Tuple[str, int]], **kwargs) -> None:
        """Training model"""
        print(f"Start training Qwen3-{self.model_size}-LoRA model...")
        
        # Load base model
        self._load_base_model()
        
        # Set up LoRA
        self._setup_lora(**kwargs)
        
        # Hyperparameters (use recommended values ​​from the configuration file or user-specified values)
        num_epochs = kwargs.get('num_epochs', 3)
        batch_size = kwargs.get('batch_size', self.config['recommended_batch_size'] // 2)  # LoRA requires smaller batch sizes
        learning_rate = kwargs.get('learning_rate', self.config['recommended_lr'] / 2)  # LoRA uses a smaller learning rate
        output_dir = kwargs.get('output_dir', f'./models/qwen3_lora_{self.model_size.lower()}_checkpoints')
        
        print(f"Hyperparameters: epochs={num_epochs}, batch_size={batch_size}, lr={learning_rate}")
        
        # Create command format data
        train_dataset = self._create_instruction_data(train_data)
        
        # participle
        tokenized_dataset = train_dataset.map(
            self._tokenize_function,
            batched=True,
            remove_columns=train_dataset.column_names
        )
        
        # training parameters
        training_args = TrainingArguments(
            output_dir=output_dir,
            num_train_epochs=num_epochs,
            per_device_train_batch_size=batch_size,
            gradient_accumulation_steps=2,
            learning_rate=learning_rate,
            logging_steps=10,
            save_steps=100,
            save_total_limit=2,
            remove_unused_columns=False,
            dataloader_drop_last=False,
            report_to=None,
        )
        
        # data organizer
        data_collator = DataCollatorForLanguageModeling(
            tokenizer=self.tokenizer,
            mlm=False,
        )
        
        # Create a trainer
        trainer = Trainer(
            model=self.lora_model,
            args=training_args,
            train_dataset=tokenized_dataset,
            data_collator=data_collator,
            tokenizer=self.tokenizer,
        )
        
        # Start training
        print(f"Start LoRA fine-tuning...")
        trainer.train()
        
        # Save model
        self.lora_model.save_pretrained(output_dir)
        self.tokenizer.save_pretrained(output_dir)
        
        self.model = self.lora_model
        self.is_trained = True
        print(f"Qwen3-{self.model_size}-LoRA model training completed!")
    
    def _extract_sentiment(self, generated_text: str, instruction: str) -> int:
        """Extract sentiment labels from generated text"""
        response = generated_text[len(instruction):].strip()
        
        if "front" in response:
            return 1
        elif "Negative" in response:
            return 0
        else:
            return 0
    
    def predict(self, texts: List[str]) -> List[int]:
        """Predict text sentiment"""
        if not self.is_trained:
            raise ValueError(f"Model {self.model_name} has not been trained yet")
        
        predictions = []
        
        self.lora_model.eval()
        with torch.no_grad():
            for text in tqdm(texts, desc=f"Qwen3-{self.model_size} is predicting"):
                pred, _ = self.predict_single(text)
                predictions.append(pred)
        
        return predictions
    
    def predict_single(self, text: str) -> Tuple[int, float]:
        """Predicting the sentiment of a single text"""
        if not self.is_trained:
            raise ValueError(f"Model {self.model_name} has not been trained yet")
        
        # Build instructions
        instruction = f"Please analyze the emotional tendency of the following Weibo text and answer 'positive' or 'negative'. \n\nText: {text}\n\nEmotion:"
        
        # participle
        inputs = self.tokenizer(instruction, return_tensors="pt")
        if torch.cuda.is_available():
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
        
        # generate answer
        self.lora_model.eval()
        with torch.no_grad():
            outputs = self.lora_model.generate(
                **inputs,
                max_new_tokens=10,
                do_sample=True,
                temperature=0.1,
                pad_token_id=self.tokenizer.pad_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
            )
        
        # Decode the generated text
        generated_text = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        
        # Extract sentiment labels
        prediction = self._extract_sentiment(generated_text, instruction)
        confidence = 0.8  # The confidence calculation of the generative model is more complicated. Here is a fixed value.
        
        return prediction, confidence
    
    def save_model(self, model_path: str = None) -> None:
        """Save model"""
        if not self.is_trained:
            raise ValueError(f"Model {self.model_name} has not been trained yet")
        
        if model_path is None:
            model_path = MODEL_PATHS["lora"][self.model_size]
        
        os.makedirs(model_path, exist_ok=True)
        
        # Save LoRA weights
        self.lora_model.save_pretrained(model_path)
        self.tokenizer.save_pretrained(model_path)
        
        print(f"LoRA model saved to: {model_path}")
    
    def load_model(self, model_path: str) -> None:
        """Load model"""
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model file does not exist: {model_path}")
        
        # Load base model
        self._load_base_model()
        
        # Load LoRA weights
        self.lora_model = PeftModel.from_pretrained(self.base_model, model_path)
        
        self.model = self.lora_model
        self.is_trained = True
        print(f"Loaded Qwen3-{self.model_size}-LoRA model: {model_path}")


def main():
    """main function"""
    parser = argparse.ArgumentParser(description='Qwen3-LoRA通用训练脚本')
    parser.add_argument('--model_size', type=str, choices=['0.6B', '4B', '8B'], 
                        help='模型大小')
    parser.add_argument('--train_path', type=str, default='./dataset/train.txt',
                        help='训练数据路径')
    parser.add_argument('--test_path', type=str, default='./dataset/test.txt',
                        help='测试数据路径')
    parser.add_argument('--model_path', type=str, help='模型保存路径（可选）')
    parser.add_argument('--epochs', type=int, default=3, help='训练轮数')
    parser.add_argument('--batch_size', type=int, help='批大小（可选，使用推荐值）')
    parser.add_argument('--learning_rate', type=float, help='学习率（可选，使用推荐值）')
    parser.add_argument('--lora_r', type=int, help='LoRA秩（可选，使用推荐值）')
    parser.add_argument('--max_samples', type=int, default=0, help='最大训练样本数（0表示使用全部数据）')
    parser.add_argument('--eval_only', action='store_true', help='仅评估模式')
    
    args = parser.parse_args()
    
    # If no model size is specified, the user is asked
    if not args.model_size:
        print("Qwen3-LoRA model training")
        print("="*40)
        print("Available model sizes:")
        print("1. 0.6B - lightweight, fast training, requires about 8GB of video memory")
        print("2. 4B - Medium size, balanced performance, video memory requirement of about 32GB") 
        print("3. 8B - Large scale, best performance, video memory requirement is about 64GB")
        print("\nNote: LoRA fine-tuning requires more video memory than the Embedding method")
        
        while True:
            choice = input("\nPlease select model size (1/2/3):").strip()
            if choice == '1':
                args.model_size = '0.6B'
                break
            elif choice == '2':
                args.model_size = '4B'
                break
            elif choice == '3':
                args.model_size = '8B'
                break
            else:
                print("Invalid selection, please enter 1, 2 or 3")
        
        print(f"Selected: Qwen3-{args.model_size} + LoRA")
        print()
    
    # Make sure the models directory exists
    os.makedirs('./models', exist_ok=True)
    
    # Create model
    model = Qwen3LoRAUniversal(args.model_size)
    
    # Determine the model saving path
    model_path = args.model_path or MODEL_PATHS["lora"][args.model_size]
    
    if args.eval_only:
        # Evaluate mode only
        print(f"Evaluation mode: Load Qwen3-{args.model_size}-LoRA model")
        model.load_model(model_path)
        
        _, test_data = BaseQwenModel.load_data(args.train_path, args.test_path)
        # LoRA evaluation uses small amounts of data
        test_subset = test_data[:50]
        model.evaluate(test_subset)
    else:
        # training mode
        train_data, test_data = BaseQwenModel.load_data(args.train_path, args.test_path)
        
        # Training data processing
        if args.max_samples > 0:
            train_subset = train_data[:args.max_samples]
            print(f"Use {len(train_subset)} pieces of data for LoRA training")
        else:
            train_subset = train_data
            print(f"Use all {len(train_subset)} pieces of data for LoRA training")
        
        # Prepare training parameters
        train_kwargs = {'num_epochs': args.epochs}
        if args.batch_size:
            train_kwargs['batch_size'] = args.batch_size
        if args.learning_rate:
            train_kwargs['learning_rate'] = args.learning_rate
        if args.lora_r:
            train_kwargs['lora_r'] = args.lora_r
        
        # Training model
        model.train(train_subset, **train_kwargs)
        
        # Evaluate the model (using a small amount of test data)
        test_subset = test_data[:50]
        model.evaluate(test_subset)
        
        # Save model
        model.save_model(model_path)
        
        # Example forecast
        print(f"\nQwen3-{args.model_size}-LoRA example prediction:")
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