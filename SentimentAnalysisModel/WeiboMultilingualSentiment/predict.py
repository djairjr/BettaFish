import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline
import re

def preprocess_text(text):
    """Simple text preprocessing for multilingual text"""
    return text

def main():
    print("Loading multilingual sentiment analysis model...")
    
    # Use multilingual sentiment analysis models
    model_name = "tabularisai/multilingual-sentiment-analysis"
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
        
        # Sentiment label mapping (5-level classification)
        sentiment_map = {
            0: "very negative", 1: "Negative", 2: "neutral", 3: "front", 4: "Very positive"
        }
        
    except Exception as e:
        print(f"Model loading failed: {e}")
        print("Please check network connection")
        return
    
    print("\n============== Multi-language sentiment analysis =============")
    print("Supported languages: 22 languages ​​including Chinese, English, Spanish, Arabic, Japanese, and Korean")
    print("Sentiment scale: very negative, negative, neutral, positive, very positive")
    print("Enter text for analysis (type 'q' to exit):")
    print("Type 'demo' to see multilingual examples")
    
    while True:
        text = input("\nPlease enter text:")
        if text.lower() == 'q':
            break
        
        if text.lower() == 'demo':
            show_multilingual_demo(tokenizer, model, device, sentiment_map)
            continue
        
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
            label = sentiment_map[prediction]
            
            print(f"Prediction result: {label} (Confidence: {confidence:.4f})")
            
            # Show probabilities for all categories
            print("Detailed probability distribution:")
            for i, (label_name, prob) in enumerate(zip(sentiment_map.values(), probabilities[0])):
                print(f"  {label_name}: {prob:.4f}")
            
        except Exception as e:
            print(f"An error occurred while predicting: {e}")
            continue

def show_multilingual_demo(tokenizer, model, device, sentiment_map):
    """Showcase multilingual sentiment analysis example"""
    print("\n=== Multi-language sentiment analysis example ===")
    
    demo_texts = [
        # Chinese
        ("The weather is so nice today, and I’m in a great mood!", "Chinese"),
        ("The food at this restaurant tastes great!", "Chinese"),
        ("The service attitude is so bad, I am very disappointed", "Chinese"),
        
        # English
        ("I absolutely love this product!", "English"),
        ("The customer service was disappointing.", "English"),
        ("The weather is fine, nothing special.", "English"),
        
        # Japanese
        ("It's a delicious dish that's delicious!", "Japanese"),
        ("このホテルのサービスはがっかりしました。", "Japanese"),
        
        # Korean
        ("이 가게의 케이크는 정말 맛있어요！", "Korean"),
        ("서비스가 너무 별로였어요。", "Korean"),
        
        # spanish
        ("¡Me encanta cómo quedó la decoración!", "spanish"),
        ("El servicio fue terrible y muy lento.", "spanish"),
    ]
    
    for text, language in demo_texts:
        try:
            inputs = tokenizer(
                text,
                max_length=512,
                padding=True,
                truncation=True,
                return_tensors='pt'
            )
            
            inputs = {k: v.to(device) for k, v in inputs.items()}
            
            with torch.no_grad():
                outputs = model(**inputs)
                logits = outputs.logits
                probabilities = torch.softmax(logits, dim=1)
                prediction = torch.argmax(probabilities, dim=1).item()
            
            confidence = probabilities[0][prediction].item()
            label = sentiment_map[prediction]
            
            print(f"\n{language}: {text}")
            print(f"Result: {label} (Confidence: {confidence:.4f})")
            
        except Exception as e:
            print(f"Error processing {text}: {e}")
    
    print("\n=== End of example ===")
    
    '''
    正在加载多语言情感分析模型...
从本地加载模型...
模型加载成功! 使用设备: cuda

============= 多语言情感分析 =============
支持语言: 中文、英文、西班牙文、阿拉伯文、日文、韩文等22种语言
情感等级: 非常负面、负面、中性、正面、非常正面
输入文本进行分析 (输入 'q' 退出):
输入 'demo' 查看多语言示例

请输入文本: 我喜欢你
C:\Users\67093\.conda\envs\pytorch_python11\Lib\site-packages\transformers\models\distilbert\modeling_distilbert.py:401: UserWarning: 1Torch was not compiled with flash attention. (Triggered internally at C:\cb\pytorch_1000000000000\work\aten\src\ATen\native\transformers\cuda\sdp_utils.cpp:263.)
  attn_output = torch.nn.functional.scaled_dot_product_attention(
预测结果: 正面 (置信度: 0.5204)
详细概率分布:
  非常负面: 0.0329
  负面: 0.0263
  中性: 0.1987
  正面: 0.5204
  非常正面: 0.2216

请输入文本:
    '''

if __name__ == "__main__":
    main()