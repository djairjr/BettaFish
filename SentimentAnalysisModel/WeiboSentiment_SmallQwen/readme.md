# Fine-tune the Qwen3 small parameter model to complete the sentiment analysis task

<img src="https://github.com/666ghj/Weibo_PublicOpinion_AnalysisSystem/blob/main/static/image/logo_Qweb3.jpg" alt="Weibo sentiment analysis example" width="25%" />

## Project background

This folder is specially used for Weibo sentiment analysis tasks based on Alibaba Qwen3 series models. According to the latest model evaluation results, Qwen3's small parameter models (0.6B, 4B, 8B) perform well on relatively simple natural language processing tasks such as topic recognition and sentiment analysis, surpassing traditional basic models such as BERT.

The qwen 0.6B model adds a linear classifier to perform text classification and sequence annotation in specific fields. It is better than bert and qwen3 few shot learning of 235B. With limited computing power, the price-performance ratio is very high...

After some related research, I think it is a good choice to use some small parameter models of Qwen3 in this system.

Although these parameters are relatively small in the LLM era, as an individual developer with limited computing resources, it is still not easy to fine-tune them. It took four days of training on an A100. Please star.

## Question exploration

In addition, I am also curious about a question: For example, for the two models Qwen3-Embedding-0.6B and Qwen3-0.6B, for the former, I connected a classification head to do the second emotion classification, and for the latter, I performed lora fine-tuning and trained on the same data set. Which one has better effect and what are the advantages of each?

**In most cases, the effect of using Qwen3-0.6B for LoRA fine-tuning will be significantly better than using the Qwen3-Embedding-0.6B external classification header, but the performance is not as good as directly connecting the classification header. **

Therefore, this module provides two versions of **fine-tuning** and **embedded and then connected to the classification header** for all parameters for everyone to choose.

We use a table to clearly show the differences, advantages and disadvantages between the two:

| Features/Dimensions | Method A: `Qwen3-Embedding-0.6B` + classification header | Method B: `Qwen3-0.6B` + LoRA fine-tuning |
| ----------------- | ------------------------------------------------------------ | ------------------------------------------------------------ |
| **Core Idea** | **Representation Learning** | **Instruction Following** |
| **Model learning method** | Freeze the Embedding model, only train a very small classification head (such as `nn.Linear`), and learn the mapping from fixed text vectors to emotion labels. | Freeze most of the basic model parameters and fine-tune the model's internal attention mechanism and knowledge expression by training the LoRA "adapter" so that it can learn to generate specific answers according to instructions. |
| **Performance Cap** | **Lower**. The model's understanding ability is limited by the generic semantic representation of `Qwen3-Embedding-0.6B`, and it cannot learn the unique and subtle emotional patterns in your data set. | **Higher**. The model adjusts its understanding of language during fine-tuning to adapt to your specific tasks and data distribution, and can better capture complex emotions such as sarcasm and Internet slang. |
| **Flexibility** | **Low**. The model can only do one thing: output a classification label. Cannot be expanded.         | **High**. What the model learns is a "task skill". You can easily modify the command so that it outputs "Positive/Negative/Neutral" or even "Why is this positive?". |
| **Training resource overhead** | **Extremely low**. Just train a classification head of several KB to several MB, which can be completed by ordinary CPU. The memory usage is very small. | **Higher**. Although LoRA is very efficient, it still needs to be performed on the GPU, and the entire 0.6B model and LoRA parameters need to be loaded into the video memory for backpropagation. |
| **Inference speed/cost** | **Extremely fast, extremely low**. The Embedding vector can be obtained in one forward propagation, and the classification head calculation can be ignored. Ideal for large-scale, low-latency production environments. | **Slower, higher**. Autoregressive generation is required (hopping from word to word), even if the answer is short (like "positive"), it is orders of magnitude slower than a one-shot forward propagation. |
| **Implementation Complexity** | **Simple**. Following the technical paradigm of the BERT era, the process is mature and the code is intuitive.       | **Medium**. It requires building instruction templates, configuring LoRA parameters, using SFTTrainer, etc. It is slightly more complicated than the former, but it is supported by mature frameworks. |

## Instructions for use

### Environment configuration
```bash
# Install dependencies
pip install -r requirements.txt

# Activate pytorch environment
conda activate your environment name
```

### Training model

**Embedding + classification header method:**
```bash
python qwen3_embedding_universal.py
# The program will ask to select the model size (0.6B/4B/8B)
```

**LoRA fine-tuning method:**
```bash
python qwen3_lora_universal.py  
# The program will ask to select the model size (0.6B/4B/8B)
```

**Command line parameters:**
```bash
# Specify the model directly
python qwen3_embedding_universal.py --model_size 0.6B
python qwen3_lora_universal.py --model_size 4B

# Custom parameters
python qwen3_embedding_universal.py --model_size 8B --epochs 10 --batch_size 16
```

### Predicted usage

**Interactive Forecast:**
```bash
python predict_universal.py
# The program will let you choose specific models and methods
```

**Command line prediction:**
```bash
# Specify model predictions
python predict_universal.py --model_type embedding --model_size 0.6B --text "The weather is really nice today"

#Load all models
python predict_universal.py --load_all --text "This movie is great"
```

### Notes

1. **Video memory requirements**:
- 0.6B: Minimum 4GB video memory
- 4B: Minimum 16GB video memory
- 8B: Minimum 32GB video memory

2. **Data format**: The format of each line is `text content\tlabel`, and the label is 0 (negative) or 1 (positive)

3. **Model Selection**: For first time use, it is recommended to start testing with the 0.6B model.

4. **Training time**: LoRA fine-tuning takes longer than the Embedding method. It is recommended to use GPU acceleration.