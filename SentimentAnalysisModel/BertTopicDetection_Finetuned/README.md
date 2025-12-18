## Topic classification (BERT Chinese base)

This directory provides a Chinese topic classification implementation using `google-bert/bert-base-chinese`:
- Automatically handle local/cache/remote three-stage loading logic;
- `train.py` performs fine-tuning training; `predict.py` performs single or interactive prediction;
- All models and weights are saved to `model/` in this directory.

Reference model card: [google-bert/bert-base-chinese](https://huggingface.co/google-bert/bert-base-chinese)

### Dataset Highlights

- About **4.1 million** pre-filtered high-quality questions and responses;
- Each question corresponds to a "[Topic]", covering **about 28,000** diverse topics;
- Filter from **14 million** original questions and answers and retain answers with at least **3 likes** to ensure content quality and interest;
- In addition to the question, topic and one or more replies, each reply also has the number of likes, reply ID, and replyer tag;
- After data cleaning and deduplication, it is divided into three parts: the sample is divided into a training set of **4.12 million** and a number of verification/tests (can be adjusted as needed).

> During actual training, please refer to the CSV under `dataset/`; the script will automatically recognize common column names or allow explicit specification through command parameters.

### Directory structure

```
BertTopicDetection_Finetuned/
├─ dataset/ # Placed data
├─ model/ # Training generation; also caches basic BERT
  ├─ train.py
  ├─ predict.py
  └─ README.md
```

### environment

```
pip install torch transformers scikit-learn pandas
```

Or use your existing Conda environment.

### Data format

The CSV contains at least text columns and label columns, which the script will try to identify automatically:
- Text column candidates: `text`/`content`/`sentence`/`title`/`desc`/`question`
- Label column candidates: `label`/`labels`/`category`/`topic`/`class`

To specify explicitly, use `--text_col` and `--label_col`.

### train

```
python train.py \
  --train_file ./dataset/web_text_zh_train.csv \
  --valid_file ./dataset/web_text_zh_valid.csv \
  --text_col auto \
  --label_col auto \
  --model_root ./model \
  --save_subdir bert-chinese-classifier \
  --num_epochs 10 --batch_size 16 --learning_rate 2e-5 --fp16
```

Key points:
- The first run will check `model/bert-base-chinese`; if not, try to cache it locally, if not, it will automatically download and save it;
- The training process is evaluated and saved step by step (every 1/4 epoch by default), and up to 5 recent checkpoints are retained (can be adjusted through the environment variable `SAVE_TOTAL_LIMIT`);
- Supports early stopping (default patience is 5 evaluations), and automatically rolls back to the best model when the evaluation/save strategy is consistent;
- Tokenizer, weights and `label_map.json` are saved to `model/bert-chinese-classifier/`.

### Optional Chinese base model (interactive selection before training)

Default base: `google-bert/bert-base-chinese`. When starting training, if the terminal is interactive, the program will prompt you to choose from the following options (or enter any Hugging Face model ID):

1) `google-bert/bert-base-chinese`
2) `hfl/chinese-roberta-wwm-ext-large`
3) `hfl/chinese-macbert-large`
4) `IDEA-CCNL/Erlangshen-DeBERTa-v2-710M-Chinese`
5) `IDEA-CCNL/Erlangshen-DeBERTa-v3-Base-Chinese`
6) `Langboat/mengzi-bert-base`
7) `BAAI/bge-base-zh` (more suitable for retrieval/contrast learning paradigm)
8) `nghuyong/ernie-3.0-base-zh`

illustrate:
- In non-interactive environments (such as scheduling systems) or when `NON_INTERACTIVE=1` is set, the model specified by the command line parameter `--pretrained_name` will be used directly (default is `google-bert/bert-base-chinese`).
- After selection, the basic model will be downloaded/cached to the `model/` directory for unified management.

### predict

Single item:
```
python predict.py --text "Which topic is this Weibo discussing?" --model_root ./model --finetuned_subdir bert-chinese-classifier
```

Interaction:
```
python predict.py --interactive --model_root ./model --finetuned_subdir bert-chinese-classifier
```

Example output:
```
Prediction: Sports-Football (Confidence: 0.9412)
```

### illustrate

- Both training and prediction have built-in simple Chinese text cleaning.
- The label set is based on the training set, and the script automatically generates and saves `label_map.json`.

### Training strategy (brief description)

- Base: `google-bert/bert-base-chinese`; classification head dimension = number of unique labels in the training set.
- Learning rate and regularization: `lr=2e-5`, `weight_decay=0.01`, which can be fine-tuned to `1e-5~3e-5` on large data.
- Sequence length and batch size: `max_length=128`, `batch_size=16`; if truncation is serious, it can be increased to 256 (increased cost).
- Warmup: If the environment supports it, use `warmup_ratio=0.1`; otherwise fall back to `warmup_steps=0`.
- Evaluate/save: press `--eval_fraction` to convert steps (default 0.25), `save_total_limit=5` to limit disk usage.
- Early stop: monitor weighted F1 (the bigger the better), default patience 5, improvement threshold 0.0.
- Stable operation on a single card: only one GPU is used by default, which can be specified through `--gpu`; the script will clean up the distributed environment variables.


### Author's note (about ultra-large-scale multi-classification)

- When topic categories reach tens of thousands, connecting a single linear classification head (large softmax) directly after the encoder is often limited: long-tail categories are difficult to learn, semantics are sparse, new topics cannot be incrementally adapted, and frequent retraining is required after going online.
-Improvement ideas (recommended priority):
- Retrieval/twin-tower paradigm (text vs. topic name/description comparative learning) + nearest neighbor retrieval + small head rearrangement, naturally supports incremental category expansion and rapid updates;
- Hierarchical classification (first rough classification and then subdivision), significantly reducing the difficulty and calculation of single head;
- Text-tag joint modeling (using tag descriptions) to improve the transferability of similar topics;
- Training details: class-balanced/focal/label smoothing, sampled softmax, contrast pre-training, etc.
- Important statement: The "static classification header fine-tuning" used in this directory is only used as an alternative and learning reference. For English/multilingual micro-essay scenarios, topics change extremely fast and traditional static classifiers are difficult to cover in time. Our work focuses on generative/self-supervised topic discovery and dynamic system construction such as `TopicGPT`; this implementation aims to provide a runnable baseline and engineering example.


