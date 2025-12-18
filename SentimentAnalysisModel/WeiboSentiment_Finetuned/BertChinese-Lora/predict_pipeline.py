from transformers import pipeline
import re

def preprocess_text(text):
    """Simple text preprocessing"""
    text = re.sub(r"\{%.+?%\}", " ", text)           # Remove {%xxx%}
    text = re.sub(r"@.+?( |$)", " ", text)           # Remove @xxx
    text = re.sub(r"【.+?】", " ", text)              # Remove【xx】
    text = re.sub(r"\u200b", " ", text)              # Remove special characters
    # Remove emoji
    text = re.sub(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U00002600-\U000027BF\U0001f900-\U0001f9ff\U0001f018-\U0001f270\U0000231a-\U0000231b\U0000238d-\U0000238d\U000024c2-\U0001f251]+', '', text)
    text = re.sub(r"\s+", " ", text)                 # Combine multiple spaces
    return text.strip()

def main():
    print("Loading Weibo sentiment analysis model...")
    
    # Use the pipeline method - simpler
    model_name = "wsqstar/GISchat-weibo-100k-fine-tuned-bert"
    local_model_path = "./model"
    
    try:
        # Check if the model already exists locally
        import os
        if os.path.exists(local_model_path):
            print("Load model from local...")
            classifier = pipeline(
                "text-classification", 
                model=local_model_path,
                return_all_scores=True
            )
        else:
            print("First time use, downloading model to local...")
            # Download the model first
            from transformers import AutoTokenizer, AutoModelForSequenceClassification
            tokenizer = AutoTokenizer.from_pretrained(model_name)
            model = AutoModelForSequenceClassification.from_pretrained(model_name)
            
            # Save to local
            tokenizer.save_pretrained(local_model_path)
            model.save_pretrained(local_model_path)
            print(f"Model saved to: {local_model_path}")
            
            # Create a pipeline using a local model
            classifier = pipeline(
                "text-classification", 
                model=local_model_path,
                return_all_scores=True
            )
        print("Model loaded successfully!")
        
    except Exception as e:
        print(f"Model loading failed: {e}")
        print("Please check network connection")
        return
    
    print("\n============== Weibo Sentiment Analysis (Pipeline version) =============")
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
            
            # predict
            outputs = classifier(processed_text)
            
            # Parse results
            positive_score = None
            negative_score = None
            
            for output in outputs[0]:
                if output['label'] == 'LABEL_1':  # front
                    positive_score = output['score']
                elif output['label'] == 'LABEL_0':  # Negative
                    negative_score = output['score']
            
            # Determine prediction results
            if positive_score > negative_score:
                label = "positive emotions"
                confidence = positive_score
            else:
                label = "negative emotions"
                confidence = negative_score
            
            print(f"Prediction result: {label} (Confidence: {confidence:.4f})")
            
        except Exception as e:
            print(f"An error occurred while predicting: {e}")
            continue

if __name__ == "__main__":
    main()