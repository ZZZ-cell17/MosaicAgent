from urllib.parse import urlsplit
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from server import app
from genie_tool.tool.mrag.config import MODEL_REQUIREMENTS
from genie_tool.tool.mrag.api.routes import document as document_route
from genie_tool.tool.mrag.api.routes import query as query_route
from genie_tool.tool.mrag.query.models import AgentEvent, AgentEventType
from genie_tool.tool.mrag.storage.qdrant_vector_store import (
    QdrantGenericVectorStore,
    QdrantVectorStore,
)
from genie_tool.tool.mrag.storage.store_factory import get_kb_file_store


client = TestClient(app)


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "mosaic-agent"}


def test_core_routes_are_registered():
    paths = set(app.openapi()["paths"])

    assert "/v1/documents/upload" in paths
    assert "/v1/mrag/query" in paths
    assert "/v1/storage/local/{file_id}/{filename}" in paths
    assert "/ready" in paths


def test_ready_reports_missing_model_settings(monkeypatch):
    for requirements in MODEL_REQUIREMENTS.values():
        for name in requirements:
            monkeypatch.delenv(name, raising=False)

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "configuration_required"
    assert response.json()["storage"]["mode"] == "local"


def test_upload_uses_mrag_local_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path))
    monkeypatch.setenv("SERVER_BASE_URL", "http://testserver")

    upload = client.post(
        "/v1/documents/upload",
        files={"file": ("lesson.txt", b"mosaic rag", "text/plain")},
    )

    assert upload.status_code == 200
    file_url = upload.json()["data"]["permanent_url"]
    download = client.get(urlsplit(file_url).path)
    assert download.status_code == 200
    assert download.content == b"mosaic rag"


def test_add_uploaded_files_returns_trackable_task_ids(tmp_path, monkeypatch):
    class FakeFileStore:
        records = []

        def add_file(self, record):
            self.records.append(record)
            return True

    file_store = FakeFileStore()
    uploaded = tmp_path / "upload-id" / "lesson.md"
    uploaded.parent.mkdir()
    uploaded.write_text("mosaic rag", encoding="utf-8")
    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path))
    monkeypatch.setenv("SERVER_BASE_URL", "http://testserver")
    monkeypatch.setattr(document_route, "get_kb_file_store", lambda: file_store)
    monkeypatch.setattr(document_route, "add_file", lambda **_kwargs: None)

    response = client.post(
        "/v1/documents/add_files",
        json={
            "kb_id": "demo-kb",
            "files": [{"filename": "lesson.md", "document_id": "upload-id"}],
        },
    )

    task = response.json()["data"]["tasks"][0]
    assert response.status_code == 200
    assert task["filename"] == "lesson.md"
    assert task["file_id"] == file_store.records[0].file_id
    assert file_store.records[0].file_status == "PENDING"


def test_mrag_query_stream(monkeypatch):
    class FakeAgent:
        def __init__(self, kb_id, n_round):
            assert kb_id == "demo-kb"
            assert n_round == 2

        @staticmethod
        def run_events(question, image_urls):
            assert question == "What is MosaicAgent?"
            assert image_urls == []
            yield AgentEvent(
                event=AgentEventType.ANSWER_DELTA,
                run_id="test-run",
                data={"content": "answer"},
            )
            yield AgentEvent(
                event=AgentEventType.RUN_COMPLETED,
                run_id="test-run",
                data={"stop_reason": "evidence_sufficient"},
            )

    monkeypatch.setenv("MRAG_MAX_ROUNDS", "2")
    monkeypatch.setattr(query_route, "get_missing_model_settings", lambda: [])
    monkeypatch.setattr(query_route, "AgenticRAG", FakeAgent)

    response = client.post(
        "/v1/mrag/query",
        json={"question": "What is MosaicAgent?", "kb_id": "demo-kb"},
    )

    assert response.status_code == 200
    assert "event: answer_delta" in response.text
    assert '"content":"answer"' in response.text
    assert "event: run_completed" in response.text
    assert "[DONE]" in response.text


def test_local_qdrant_vector_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("QDRANT_MODE", "local")
    monkeypatch.setenv("QDRANT_PATH", str(tmp_path / "qdrant"))
    store = QdrantVectorStore({})

    try:
        assert store.create_collection("roundtrip", vector_size=3)
        assert store.add_vectors(
            "roundtrip",
            vectors=[[1.0, 0.0, 0.0]],
            payloads=[{"kb_id": "demo", "text": "MosaicAgent"}],
        )

        results = store.search_vectors(
            "roundtrip",
            query_vectors=[[1.0, 0.0, 0.0]],
            filter_conditions={"kb_id": "demo"},
        )

        assert results[0][0]["payload"]["text"] == "MosaicAgent"
    finally:
        store.client.close()


def test_multimodal_store_deletes_vectors_by_file_id(tmp_path, monkeypatch):
    monkeypatch.setenv("QDRANT_MODE", "local")
    monkeypatch.setenv("QDRANT_PATH", str(tmp_path / "qdrant-delete"))
    store = QdrantVectorStore({})
    collection = QdrantGenericVectorStore(store, "images", embedding_size=3)

    try:
        assert collection.create_collection()
        assert collection.add_images([
            {
                "kb_id": "demo",
                "file_id": "remove-me",
                "vector": [1.0, 0.0, 0.0],
            }
        ])
        assert collection.delete_by_file_ids("demo", ["remove-me"])
        assert store.count_vectors("images", {"kb_id": "demo"}) == 0
    finally:
        store.client.close()


def test_sqlite_file_store_is_singleton_under_concurrency():
    with ThreadPoolExecutor(max_workers=8) as executor:
        stores = list(executor.map(lambda _: get_kb_file_store(), range(16)))

    assert len({id(store) for store in stores}) == 1
