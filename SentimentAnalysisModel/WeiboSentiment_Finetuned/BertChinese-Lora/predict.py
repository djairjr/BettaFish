import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline
import re

def preprocess_text(text):
    return text

def main():
    print("Loading Weibo sentiment analysis model...")
    
    # Pre-trained model using HuggingFace
    model_name = "wsqstar/GISchat-weibo-100k-fine-tuned-bert"
    local_model_path = "./model"
    
    try:
        # Check if the model already exists locally
        import os
        if os.path.exists(local_model_path):
            print("Load model from local...")
            tokenizer = AutoTokenizer.from_pretrained(local_model_path)
            model = AutoModelForSequenceClassification.from_pretrained(local_model_path)
        else:
            print("First time use, downloading model to local...")
            # Download and save locally
            tokenizer = AutoTokenizer.from_pretrained(model_name)
            model = AutoModelForSequenceClassification.from_pretrained(model_name)
            
            # Save to local
            tokenizer.save_pretrained(local_model_path)
            model.save_pretrained(local_model_path)
            print(f"Model saved to: {local_model_path}")
        
        # Set up the device
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        model.to(device)
        model.eval()
        print(f"Model loaded successfully! Device used: {device}")
        
    except Exception as e:
        print(f"Model loading failed: {e}")
        print("Please check the network connection or use pipeline method")
        return
    
    print("\n============= Weibo Sentiment Analysis =============")
    print("Enter Weibo content for analysis (enter 'q' to exit):")
    
    while True:
        text = input("\nPlease enter Weibo content:")
        if text.lower() == 'q':
            break
        
        if not text.strip():
            print("The input cannot be empty, please re-enter")
            continue
        
        try:
            # Preprocess text
            processed_text = preprocess_text(text)
            
            # word segmentation coding
            inputs = tokenizer(
                processed_text,
                max_length=512,
                padding=True,
                truncation=True,
                return_tensors='pt'
            )
            
            # Transfer to device
            inputs = {k: v.to(device) for k, v in inputs.items()}
            
            # predict
            with torch.no_grad():
                outputs = model(**inputs)
                logits = outputs.logits
                probabilities = torch.softmax(logits, dim=1)
                prediction = torch.argmax(probabilities, dim=1).item()
            
            # Output results
            confidence = probabilities[0][prediction].item()
            label = "positive emotions" if prediction == 1 else "negative emotions"
            
            print(f"Prediction result: {label} (Confidence: {confidence:.4f})")
            
        except Exception as e:
            print(f"An error occurred while predicting: {e}")
            continue

if __name__ == "__main__":
    main()