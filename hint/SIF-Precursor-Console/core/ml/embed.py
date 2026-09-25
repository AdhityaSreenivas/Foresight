import os

os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

import torch
from transformers import AutoTokenizer, AutoModel


MODEL_NAME = "roberta-base"

tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModel.from_pretrained(MODEL_NAME)

model.eval()


def get_embedding(text):

    encoded = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        max_length=512,
        padding=True
    )

    with torch.no_grad():

        output = model(**encoded)

    token_embeddings = output.last_hidden_state

    attention_mask = encoded["attention_mask"]

    mask = attention_mask.unsqueeze(-1)

    masked_embeddings = token_embeddings * mask

    summed = masked_embeddings.sum(dim=1)

    counts = mask.sum(dim=1).clamp(min=1)

    embedding = summed / counts

    return embedding[0].numpy()