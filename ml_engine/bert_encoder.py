"""
PSIF Platform — BERT Text Encoder

Encodes composite_narrative strings into fixed-size dense vectors using
a frozen (non-finetuned) distilbert-base-uncased model as a feature extractor.

Design choices (from specification §6, Step 1):
  - Model: distilbert-base-uncased (configurable via BERT_MODEL_NAME in .env)
  - Pooling: mean-pooling over all token embeddings (excluding padding tokens).
    Mean-pooling generally performs at least as well as CLS-token pooling
    and is simple.  This choice must remain consistent between training and
    inference (it is).
  - Truncation: at 512 tokens (the model's max_length).  Narratives longer
    than 512 tokens are silently truncated.  This is documented behaviour —
    a sliding-window approach is a future improvement.
  - No fine-tuning: BERT weights are frozen (torch.no_grad()).  The model
    is used purely as a feature extractor.  Fine-tuning once a larger
    labeled PSIF dataset exists is the recommended next step.
  - Batching: forward passes are batched (default batch_size=32) for
    efficiency on both CPU and GPU.  One-at-a-time encoding would be ~32×
    slower on a dataset.

Output: numpy array of shape (N, hidden_size)
  - distilbert-base-uncased: hidden_size = 768
  - bert-base-uncased:       hidden_size = 768
  - Adjust if using a model with a different hidden size.
"""
import logging
from typing import Optional, Callable
import typing

import numpy as np
import torch
from transformers import AutoTokenizer, AutoModel

logger = logging.getLogger(__name__)

# Module-level singletons — loaded once and reused for all predictions.
# Avoids reloading the model (expensive) on every request.
_tokenizer: Optional[AutoTokenizer] = None
_model: Optional[AutoModel] = None
_loaded_model_name: Optional[str] = None


def _get_model_and_tokenizer(model_name: str) -> tuple[AutoTokenizer, AutoModel]:
    """
    Lazy-load the tokenizer and model.  Reloads if model_name changes.
    Thread safety: acceptable for single-process Celery workers.
    """
    global _tokenizer, _model, _loaded_model_name

    if _model is None or _loaded_model_name != model_name:
        torch.set_num_threads(1)
        logger.info("Loading BERT model: %s (this may take a moment on first run)", model_name)
        _tokenizer = AutoTokenizer.from_pretrained(model_name)
        _model = AutoModel.from_pretrained(model_name)
        _model.eval()  # Set to evaluation mode (disables dropout etc.)
        _loaded_model_name = model_name
        logger.info("BERT model loaded: %s | hidden_size=%d",
                    model_name, _model.config.hidden_size)

    return _tokenizer, _model


def _mean_pool(token_embeddings: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
    """
    Mean-pool token embeddings, ignoring padding tokens.

    Args:
        token_embeddings: (batch, seq_len, hidden_size)
        attention_mask:   (batch, seq_len) — 1 for real tokens, 0 for padding

    Returns:
        (batch, hidden_size) pooled representations
    """
    mask = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    summed = torch.sum(token_embeddings * mask, dim=1)
    count = torch.clamp(mask.sum(dim=1), min=1e-9)
    return summed / count


def encode_texts(
    texts: list[str],
    model_name: str,
    batch_size: int = 32,
    progress_callback: typing.Optional[typing.Callable[[int, int], None]] = None,
) -> np.ndarray:
    """
    Encode a list of texts into dense vectors using the BERT model.

    Args:
        texts:             List of strings to encode (composite_narrative values).
                           Empty strings produce a zero vector.
        model_name:        HuggingFace model name or path (e.g., "distilbert-base-uncased").
        batch_size:        Number of texts to process per forward pass.
        progress_callback: Optional callback(processed_count, total_count) called per batch.

    Returns:
        numpy array of shape (len(texts), hidden_size)
    """
    if not texts:
        # Determine hidden_size dynamically instead of hardcoding 768
        _, model = _get_model_and_tokenizer(model_name)
        return np.empty((0, model.config.hidden_size))

    tokenizer, model = _get_model_and_tokenizer(model_name)
    hidden_size = model.config.hidden_size

    all_embeddings = []
    total = len(texts)

    if progress_callback:
        try:
            progress_callback(0, total)
        except Exception as cb_err:
            logger.debug("BERT initial progress_callback error: %s", cb_err)

    for batch_start in range(0, total, batch_size):
        batch_texts = texts[batch_start: batch_start + batch_size]
        batch_num = batch_start // batch_size + 1

        logger.debug("BERT encoding batch %d/%d (%d texts)",
                     batch_num, -(-total // batch_size), len(batch_texts))

        # Replace empty strings with a single space so the tokenizer doesn't error
        batch_texts = [t if t.strip() else " " for t in batch_texts]

        # Tokenize — truncate at model max_length (512 for distilbert)
        encoded = tokenizer(
            batch_texts,
            padding=True,
            truncation=True,
            max_length=tokenizer.model_max_length,
            return_tensors="pt",
        )

        with torch.no_grad():
            outputs = model(**encoded)

        # Mean-pool over token dimension
        embeddings = _mean_pool(outputs.last_hidden_state, encoded["attention_mask"])
        all_embeddings.append(embeddings.cpu().numpy())

        if progress_callback:
            try:
                processed_so_far = min(batch_start + len(batch_texts), total)
                progress_callback(processed_so_far, total)
            except Exception as cb_err:
                logger.debug("BERT progress_callback error: %s", cb_err)

    result = np.vstack(all_embeddings)
    logger.info("BERT encoding complete: %d texts → shape %s", total, result.shape)
    return result


def encode_single(text: str, model_name: str) -> np.ndarray:
    """
    Convenience wrapper to encode a single text.
    Returns a 1D array of shape (hidden_size,).
    """
    return encode_texts([text], model_name=model_name, batch_size=1)[0]
