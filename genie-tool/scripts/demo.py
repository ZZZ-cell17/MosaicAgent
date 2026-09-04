"""Run the smallest real multimodal ingestion and AgenticRAG query flow."""

import argparse
import json
import mimetypes
import sys
import time
from pathlib import Path

import requests


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FILES = (
    REPOSITORY_ROOT / "examples" / "knowledge" / "mosaic_overview.md",
    REPOSITORY_ROOT / "docs" / "img" / "mrag" / "mrag_struct.png",
)


def request_json(method: str, url: str, **kwargs) -> dict:
    response = requests.request(method, url, timeout=30, **kwargs)
    response.raise_for_status()
    return response.json()


def check_service(base_url: str):
    health = request_json("GET", f"{base_url}/health")
    print(f"[1/5] API: {health['status']}")

    response = requests.get(f"{base_url}/ready", timeout=30)
    if response.status_code != 200:
        status = response.json()
        missing = sorted({
            name
            for component in status["models"].values()
            for name in component["missing"]
        })
        raise RuntimeError("模型配置未完成: " + ", ".join(missing))
    print("[2/5] 配置: ready")


def create_knowledge_base(base_url: str, kb_id: str):
    response = requests.post(
        f"{base_url}/v1/documents/create_knowledge_base",
        json={
            "kb_id": kb_id,
            "kb_name": "MosaicAgent Demo",
            "kb_desc": "最小多模态闭环样例",
            "chunk_type": "markdown",
        },
        timeout=30,
    )
    if response.status_code == 409:
        return
    response.raise_for_status()


def upload_file(base_url: str, file_path: Path) -> dict:
    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    with file_path.open("rb") as file_handle:
        response = request_json(
            "POST",
            f"{base_url}/v1/documents/upload",
            files={"file": (file_path.name, file_handle, content_type)},
        )
    return {
        "filename": file_path.name,
        "document_id": response["data"]["document_id"],
    }


def wait_for_ingestion(base_url: str, kb_id: str, tasks: dict[str, str], timeout: int):
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = request_json(
            "POST",
            f"{base_url}/v1/documents/list_kb_files",
            json={"kb_id": kb_id, "page_no": 1, "page_size": 100},
        )
        records = {record["file_id"]: record for record in response["data"]["records"]}
        failed = [
            tasks[file_id]
            for file_id, record in records.items()
            if file_id in tasks and record["file_status"] == "FAILED"
        ]
        if failed:
            raise RuntimeError(f"文件入库失败: {', '.join(failed)}")
        if tasks.keys() <= records.keys() and all(
            records[file_id]["file_status"] == "SUCCESS" for file_id in tasks
        ):
            return
        time.sleep(2)
    raise TimeoutError(f"等待文件入库超时（{timeout} 秒）")


def stream_answer(base_url: str, kb_id: str, question: str):
    trace_labels = {
        "query_planned": "查询规划",
        "retrieval_completed": "多路检索",
        "evidence_evaluated": "证据判断",
        "rerank_completed": "文本重排",
        "route_selected": "模型路由",
    }
    with requests.post(
        f"{base_url}/v1/mrag/query",
        json={
            "kb_id": kb_id,
            "question": question,
            "image_urls": [],
            "include_trace": True,
        },
        stream=True,
        timeout=600,
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            data = line[6:]
            if data == "[DONE]":
                break
            try:
                event = json.loads(data)
                event_name = event["event"]
                event_data = event.get("data", {})
                if event_name == "answer_delta":
                    print(event_data.get("content", ""), end="", flush=True)
                elif event_name in trace_labels:
                    print(
                        f"\n[{trace_labels[event_name]}] "
                        f"{json.dumps(event_data, ensure_ascii=False)}"
                    )
                elif event_name == "run_failed":
                    raise RuntimeError(event_data.get("message", "Agent 执行失败"))
            except (KeyError, TypeError, json.JSONDecodeError):
                print(data)
    print()


def main():
    parser = argparse.ArgumentParser(description="Run the MosaicAgent MRAG demo")
    parser.add_argument("--base-url", default="http://127.0.0.1:1601")
    parser.add_argument("--kb-id", default="mosaic-demo")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--query-only", action="store_true")
    parser.add_argument(
        "--question",
        default="MosaicAgent 的入库和问答链路分别是什么？它是否保存长期记忆？",
    )
    parser.add_argument("files", nargs="*", type=Path, default=list(DEFAULT_FILES))
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    try:
        check_service(base_url)
        if not args.query_only:
            create_knowledge_base(base_url, args.kb_id)
            uploads = [upload_file(base_url, path.resolve()) for path in args.files]
            print(f"[3/5] 上传: {', '.join(item['filename'] for item in uploads)}")
            submission = request_json(
                "POST",
                f"{base_url}/v1/documents/add_files",
                json={"kb_id": args.kb_id, "files": uploads},
            )
            tasks = {
                task["file_id"]: task["filename"]
                for task in submission["data"]["tasks"]
            }
            wait_for_ingestion(base_url, args.kb_id, tasks, args.timeout)
            print("[4/5] 入库: success")
        print("[5/5] Agent 回答:")
        stream_answer(base_url, args.kb_id, args.question)
    except (requests.RequestException, RuntimeError, TimeoutError) as exc:
        print(f"Demo failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
