from types import SimpleNamespace

import pytest
from docx import Document
from fastapi.testclient import TestClient
from PIL import Image

from server import app
from genie_tool.tool.mrag.api.routes import document as document_route
from genie_tool.tool.mrag.api.routes import query as query_route
from genie_tool.tool.mrag.document.parser import DocxDocumentParser
from genie_tool.tool.mrag.document.parser import MarkdownDocumentParser
from genie_tool.tool.mrag.document.splitter import (
    MarkdownDocumentSplitter,
    get_text_splitter,
)
from genie_tool.tool.mrag.embedding.image_embedding import QwenVLEmbedding
from genie_tool.tool.mrag.generation.llm import LLMClient
from genie_tool.tool.mrag.generation.vlm import VLLMClient
from genie_tool.tool.mrag.query.agent import AgenticRAG
from genie_tool.tool.mrag.utils import download_utils
from genie_tool.tool.mrag.utils.url_utils import validate_http_url


client = TestClient(app)


class FakeDownloadResponse:
    def __init__(self, content: bytes, content_length: int | None = None):
        self._content = content
        self.status_code = 200
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)
        self.is_redirect = False
        self.is_permanent_redirect = False
        self.closed = False

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        del chunk_size
        yield self._content

    def close(self):
        self.closed = True


def test_cors_allows_frontend_but_not_arbitrary_origins():
    allowed = client.options(
        "/health",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    blocked = client.options(
        "/health",
        headers={
            "Origin": "https://malicious.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert allowed.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert "access-control-allow-origin" not in blocked.headers


def test_add_files_rejects_path_traversal():
    response = client.post(
        "/v1/documents/add_files",
        json={
            "kb_id": "demo-kb",
            "files": [{"filename": "../escape.md", "document_id": "upload-id"}],
        },
    )

    assert response.status_code == 422


def test_remote_file_and_web_import_are_disabled_by_default(monkeypatch):
    monkeypatch.setenv("ENABLE_REMOTE_FILE_IMPORT", "false")
    monkeypatch.setenv("ENABLE_WEB_IMPORT", "false")

    remote_file = client.post(
        "/v1/documents/add_files",
        json={
            "kb_id": "demo-kb",
            "files": [{"filename": "remote.md", "file_url": "https://example.com/remote.md"}],
        },
    )
    web_page = client.post(
        "/v1/documents/add_web_url",
        json={"kb_id": "demo-kb", "url": "https://example.com"},
    )

    assert remote_file.status_code == 403
    assert web_page.status_code == 403


def test_wildcard_remote_access_still_blocks_private_networks():
    with pytest.raises(ValueError, match="私网"):
        validate_http_url("http://127.0.0.1/file", allowed_hosts={"*"})

    assert validate_http_url(
        "http://127.0.0.1/file",
        allowed_hosts={"127.0.0.1"},
    ) == "http://127.0.0.1/file"


def test_download_uses_tls_and_enforces_size_limit(tmp_path, monkeypatch):
    calls = []

    def fake_get(_url, **kwargs):
        calls.append(kwargs)
        return FakeDownloadResponse(b"12345")

    monkeypatch.setattr(download_utils.requests, "get", fake_get)
    target = tmp_path / "download.txt"

    download_utils.download_file("https://example.com/file", str(target), max_bytes=5)

    assert target.read_bytes() == b"12345"
    assert calls[0]["verify"] is True
    assert calls[0]["allow_redirects"] is False

    monkeypatch.setattr(
        download_utils.requests,
        "get",
        lambda *_args, **_kwargs: FakeDownloadResponse(b"too large", content_length=9),
    )
    with pytest.raises(ValueError, match="超过"):
        download_utils.download_file(
            "https://example.com/large",
            str(tmp_path / "large.bin"),
            max_bytes=5,
        )


def test_invalid_agent_round_configuration_returns_503(monkeypatch):
    monkeypatch.setenv("MRAG_MAX_ROUNDS", "not-a-number")
    monkeypatch.setattr(query_route, "get_missing_model_settings", lambda: [])

    response = client.post(
        "/v1/mrag/query",
        json={"question": "question", "kb_id": "demo-kb"},
    )

    assert response.status_code == 503
    assert "必须是整数" in response.json()["detail"]


def test_query_rejects_untrusted_image_url(monkeypatch):
    monkeypatch.setattr(query_route, "get_missing_model_settings", lambda: [])

    response = client.post(
        "/v1/mrag/query",
        json={
            "question": "describe this image",
            "kb_id": "demo-kb",
            "image_urls": ["https://example.com/image.png"],
        },
    )

    assert response.status_code == 400
    assert "允许列表" in response.json()["detail"]


def test_knowledge_base_conflicts_and_missing_delete_are_reported(monkeypatch):
    class FakeStore:
        @staticmethod
        def create_kb(_model):
            return False

        @staticmethod
        def delete_kb(_model):
            return False

    monkeypatch.setattr(document_route, "get_kb_store", lambda: FakeStore())

    duplicate = client.post(
        "/v1/documents/create_knowledge_base",
        json={"kb_id": "demo-kb", "kb_name": "Demo"},
    )
    null_delete = client.post(
        "/v1/documents/delete_knowledge_base",
        json={"kb_id": None},
    )
    missing = client.post(
        "/v1/documents/delete_knowledge_base",
        json={"kb_id": "missing-kb"},
    )

    assert duplicate.status_code == 409
    assert null_delete.status_code == 422
    assert missing.status_code == 404


def test_delete_files_reports_when_no_file_matches(monkeypatch):
    class FakeFileStore:
        @staticmethod
        def delete_by_file_ids(_kb_id, _file_ids):
            return 0

    monkeypatch.setattr(document_route, "get_kb_file_store", lambda: FakeFileStore())

    response = client.post(
        "/v1/documents/delete_files",
        json={"kb_id": "demo-kb", "file_ids": ["missing-file"]},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "未找到可删除的文件"


def test_delete_knowledge_base_cascades_file_metadata(monkeypatch):
    deleted_kb_ids = []

    class FakeKBStore:
        @staticmethod
        def delete_kb(_model):
            return True

    class FakeFileStore:
        @staticmethod
        def delete_by_kb_id(kb_id):
            deleted_kb_ids.append(kb_id)
            return 2

    class FakeVectorStore:
        @staticmethod
        def delete_text_by_kb_id(_kb_id):
            return True

        @staticmethod
        def delete_image_by_kb_id(_kb_id):
            return True

        @staticmethod
        def delete_page_by_kb_id(_kb_id):
            return True

    monkeypatch.setattr(document_route, "get_kb_store", lambda: FakeKBStore())
    monkeypatch.setattr(document_route, "get_kb_file_store", lambda: FakeFileStore())
    monkeypatch.setattr(document_route, "VectorStore", FakeVectorStore)

    response = client.post(
        "/v1/documents/delete_knowledge_base",
        json={"kb_id": "demo-kb"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["deleted_files"] == 2
    assert deleted_kb_ids == ["demo-kb"]


def test_markdown_splitter_has_safe_defaults_and_honors_zero_overlap(monkeypatch):
    monkeypatch.delenv("CHUNK_TYPE", raising=False)
    splitter = get_text_splitter()
    custom = MarkdownDocumentSplitter(chunk_size=40, chunk_overlap=0)

    chunks = custom.split("# Heading\n\n" + "content sentence. " * 20)

    assert isinstance(splitter, MarkdownDocumentSplitter)
    assert custom._chunk_overlap == 0
    assert len(chunks) > 1


def test_docx_images_keep_their_real_extension(tmp_path):
    jpeg_path = tmp_path / "source.jpg"
    Image.new("RGB", (8, 8), "white").save(jpeg_path, format="JPEG")
    docx_path = tmp_path / "document.docx"
    document = Document()
    document.add_picture(str(jpeg_path))
    document.save(docx_path)

    parser = DocxDocumentParser(str(tmp_path / "parsed"), str(docx_path))
    parser.parse_content()
    images = parser.parsed_images()

    assert len(images) == 1
    assert images[0].lower().endswith(".jpg")
    with Image.open(images[0]) as image:
        assert image.format == "JPEG"


def test_markdown_remote_images_are_removed_when_disabled(tmp_path, monkeypatch):
    source = tmp_path / "source.md"
    source.write_text("![secret](http://127.0.0.1/private.png)", encoding="utf-8")
    monkeypatch.setenv("ENABLE_MARKDOWN_REMOTE_IMAGES", "false")
    monkeypatch.setattr(
        download_utils,
        "download_file",
        lambda *_args, **_kwargs: pytest.fail("remote image must not be downloaded"),
    )

    parser = MarkdownDocumentParser(str(tmp_path / "parsed-md"), str(source))
    parser._copy_file_to_workdir()
    parser._download_and_update_images()
    parsed = parser.parsed_text()

    assert "127.0.0.1" not in parsed
    assert "远程图片已忽略" in parsed


def test_markdown_rejects_non_relative_local_image_paths(tmp_path, monkeypatch):
    source = tmp_path / "unsafe-images.md"
    source.write_text(
        "![local](file:///etc/passwd)\n"
        "![network](//internal.example/secret.png)\n"
        "![traversal](../secret.png)\n"
        "![safe](images/diagram.png)",
        encoding="utf-8",
    )
    monkeypatch.setenv("ENABLE_MARKDOWN_REMOTE_IMAGES", "false")

    parser = MarkdownDocumentParser(str(tmp_path / "parsed-images"), str(source))
    parser._copy_file_to_workdir()
    parser._download_and_update_images()
    parsed = parser.parsed_text()

    assert "file:///" not in parsed
    assert "//internal.example" not in parsed
    assert "../secret.png" not in parsed
    assert "![safe](images/diagram.png)" in parsed
    assert parsed.count("不安全图片已忽略") == 3


def test_vlm_detects_mime_from_content_not_suffix(tmp_path):
    misleading_path = tmp_path / "jpeg-named-png.png"
    Image.new("RGB", (8, 8), "white").save(misleading_path, format="JPEG")

    messages = VLLMClient.convert_messages_with_image_path("describe", str(misleading_path))
    data_url = messages[0]["content"][1]["image_url"]["url"]

    assert data_url.startswith("data:image/jpeg;base64,")


def test_multimodal_embedding_http_error_is_not_silenced():
    response = SimpleNamespace(status_code=500)

    with pytest.raises(RuntimeError, match="HTTP 500"):
        QwenVLEmbedding._extract_embedding(response, "图片")


def test_qwen_thinking_options_can_be_disabled(monkeypatch):
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="answer"))]
        )

    client = LLMClient.__new__(LLMClient)
    client.model_name = "portable-model"
    client.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    monkeypatch.setenv("LLM_SEND_THINKING_OPTIONS", "false")

    assert client.completions([{"role": "user", "content": "question"}]) == "answer"
    assert "extra_body" not in captured


def test_reference_context_matches_answer_citation_format():
    context = AgenticRAG.build_ref_context([
        {"payload": {"text": "source text"}},
    ])

    assert context == "〔1〕\nsource text"
