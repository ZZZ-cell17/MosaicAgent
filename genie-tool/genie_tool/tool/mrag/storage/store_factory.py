import os
import threading
from pathlib import Path

from sqlalchemy import create_engine

from .kb_doc_store import KBDocStore
from .kb_file_store import KBFileStore
from .kb_store import KBStore

_sqlite_engine = None
_kb_store = None
_kb_file_store = None
_kb_doc_store = None
_store_lock = threading.Lock()

store_type = os.getenv("STORE_TYPE", "sqlite")

if store_type == "sqlite":
    local_path = os.getenv("SQLITE_PATH", "kb_file.db")
    Path(local_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    _sqlite_engine = create_engine(f"sqlite:///{local_path}")

def get_kb_file_store() -> KBFileStore:
    global _kb_file_store
    if store_type != "sqlite":
        raise Exception("Unknown store type")
    if _kb_file_store is None:
        with _store_lock:
            if _kb_file_store is None:
                from .kb_file_store_sqlite_impl import KBFileSQLite
                _kb_file_store = KBFileSQLite(_sqlite_engine)
    return _kb_file_store


def get_kb_store() -> KBStore:
    global _kb_store
    if store_type != "sqlite":
        raise Exception("Unknown store type")
    if _kb_store is None:
        with _store_lock:
            if _kb_store is None:
                from .kb_store_sqlite_impl import KBStoreSQLite
                _kb_store = KBStoreSQLite(_sqlite_engine)
    return _kb_store


def get_kb_doc_store() -> KBDocStore:
    global _kb_doc_store
    if store_type != "sqlite":
        raise Exception("Unknown store type")
    if _kb_doc_store is None:
        with _store_lock:
            if _kb_doc_store is None:
                from .kb_doc_store_sqlite_impl import KBDocSQLite
                _kb_doc_store = KBDocSQLite(_sqlite_engine)
    return _kb_doc_store
