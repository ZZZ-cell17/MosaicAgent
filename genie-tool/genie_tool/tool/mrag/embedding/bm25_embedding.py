import os
from pathlib import Path

import dotenv

dotenv.load_dotenv()

from fastembed import SparseTextEmbedding


class BM25Embedding:
    def __init__(self):
        cache_dir = Path(os.getenv("FASTEMBED_CACHE_PATH", "./data/fastembed")).expanduser().resolve()
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._model = SparseTextEmbedding("Qdrant/bm25", cache_dir=str(cache_dir))

    def encode_text_batch(self, texts: list[str]) -> list[dict]:
        embeddings = self._model.embed(texts)
        return [embedding.as_object() for embedding in embeddings]


def get_bm25_embedding_model() -> BM25Embedding:
    return BM25Embedding()
