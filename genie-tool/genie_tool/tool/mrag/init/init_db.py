"""Initialize MosaicAgent vector collections and SQLite knowledge-base metadata."""

import argparse
import json
import os
from datetime import datetime

import dotenv

from genie_tool.tool.mrag.storage import VectorStore
from genie_tool.tool.mrag.storage.models.kb_model import KBModel
from genie_tool.tool.mrag.storage.store_factory import (
    get_kb_doc_store,
    get_kb_file_store,
    get_kb_store,
)


dotenv.load_dotenv()


def initialize_storage(kb_id: str, kb_name: str = "MosaicAgent Demo") -> dict:
    if not kb_id:
        raise ValueError("kb_id is required")

    vector_store = VectorStore()
    collection_results = {
        "text": vector_store.text_store.create_collection(),
        "image": vector_store.image_store.create_collection(),
        "page": vector_store.page_store.create_collection(),
    }
    if not all(collection_results.values()):
        raise RuntimeError(f"Failed to initialize vector collections: {collection_results}")

    now = datetime.now()
    kb_model = KBModel(
        kb_id=kb_id,
        kb_name=kb_name,
        kb_desc="MosaicAgent multimodal RAG learning knowledge base",
        chunk_type=os.getenv("CHUNK_TYPE", "markdown"),
        chunk_size=int(os.getenv("CHUNK_SIZE", "500")),
        chunk_overlap_size=int(os.getenv("CHUNK_OVERLAP", "100")),
        deleted=0,
        create_time=now,
        modify_time=now,
    )
    kb_store = get_kb_store()
    get_kb_file_store()
    get_kb_doc_store()
    created = kb_store.create_kb(kb_model)

    return {
        "kb_id": kb_id,
        "knowledge_base": "created" if created else "already_exists",
        "collections": collection_results,
        "qdrant_mode": os.getenv("QDRANT_MODE", "local"),
    }


def main():
    parser = argparse.ArgumentParser(description="Initialize MosaicAgent storage")
    parser.add_argument("--kb-id", default=os.getenv("DEFAULT_KB_ID", "mosaic-demo"))
    parser.add_argument("--kb-name", default="MosaicAgent Demo")
    args = parser.parse_args()

    try:
        result = initialize_storage(args.kb_id, args.kb_name)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        VectorStore().close()


if __name__ == "__main__":
    main()
