"""Run the bounded BM25 baseline against an external frozen expert benchmark.

The evaluator reads raw query/source text only in memory and writes metadata
results (never query text, source text, tokens, or complete responses).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from collections import Counter
from pathlib import Path
from typing import Any

from backend.common import ObjectScope
from backend.rag.bm25 import Bm25Document, Bm25Index, Bm25Request, tokenize_bm25
from backend.rag.chunk_baseline import (
    ChunkBaselineManifest,
    validate_corrected_chunk_baseline_manifest,
)

PRODUCT_IDS = {
    "DJI Mini 3": "9278439686282",
    "DJI Air 3": "9278460821642",
    "DJI Mavic 3": "9278439719050",
}
STORE_ID = "shopify-store:bys-user-store-578412-7a11gk0u"
STORE_KEY = "bys-user-store-578412-7a11gk0u.myshopify.com"
VARIANT_IDS = {
    PRODUCT_IDS["DJI Mini 3"]: "50107364802698",
    PRODUCT_IDS["DJI Air 3"]: "50107426603146",
    PRODUCT_IDS["DJI Mavic 3"]: "50107364901002",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _source_version(locator: dict[str, Any]) -> str:
    return str(locator["document_version"])


def _build_documents(
    locator_dir: Path,
    overlay_path: Path,
    chunk_manifest: ChunkBaselineManifest,
) -> tuple[Bm25Document, ...]:
    """Build documents only after validating against the admitted baseline."""
    overlay = _load_json(overlay_path)
    excluded_pages = set(
        overlay["excluded_from_future_mavic_3_retrieval_pending_section_review"]
    )
    baseline_records = {
        (record.source_id, record.page_number): record
        for record in chunk_manifest.records
    }
    if len(baseline_records) != len(chunk_manifest.records):
        raise ValueError("chunk baseline contains duplicate source/page records")
    seen_records: set[tuple[str, int]] = set()
    documents: list[Bm25Document] = []
    for path in sorted(locator_dir.glob("*.jsonl")):
        for locator in _load_jsonl(path):
            source_id = locator["source_id"]
            page_number = int(locator["page_number"])
            if source_id == overlay["source_id"] and page_number in excluded_pages:
                continue
            raw_text = str(locator.get("verbatim_text", ""))
            text = raw_text.strip()
            if not text:
                continue
            baseline = baseline_records.get((source_id, page_number))
            if baseline is None:
                raise ValueError(
                    f"locator is absent from chunk baseline: {source_id}:{page_number}"
                )
            text_sha256 = hashlib.sha256(raw_text.encode()).hexdigest()
            if text_sha256 != locator.get("text_sha256"):
                raise ValueError(
                    f"locator text checksum mismatch: {source_id}:{page_number}"
                )
            if baseline.source_version != _source_version(locator):
                raise ValueError(
                    "locator/baseline source_version mismatch: "
                    f"{source_id}:{page_number}"
                )
            if baseline.store_id != STORE_KEY:
                raise ValueError(
                    f"unexpected corpus store_id: {source_id}:{page_number}"
                )
            if locator.get("store_id", baseline.store_id) != baseline.store_id:
                raise ValueError(
                    f"locator/baseline store_id mismatch: {source_id}:{page_number}"
                )
            if locator.get("variant_id", baseline.variant_id) != baseline.variant_id:
                raise ValueError(
                    f"locator/baseline variant_id mismatch: {source_id}:{page_number}"
                )
            if baseline.text_sha256 != text_sha256:
                raise ValueError(
                    f"baseline text checksum mismatch: {source_id}:{page_number}"
                )
            if baseline.product_id not in PRODUCT_IDS:
                raise ValueError(f"unmapped baseline product: {baseline.product_id}")
            seen_records.add((source_id, page_number))
            source_version = baseline.source_version
            document_id = f"{source_id}::page:{page_number}"
            documents.append(
                Bm25Document(
                    document_id=document_id,
                    text=text,
                    store_id=STORE_ID,
                    product_id=PRODUCT_IDS[baseline.product_id],
                    variant_id=baseline.variant_id,
                    source_id=source_id,
                    source_version=source_version,
                    locator=baseline.locator,
                    text_sha256=text_sha256,
                    page_number=page_number,
                    token_estimate=max(1, len(tokenize_bm25(text))),
                )
            )
    excluded_records = {
        (overlay["source_id"], page_number) for page_number in excluded_pages
    }
    expected_records = set(baseline_records) - excluded_records
    if seen_records != expected_records:
        missing_records = sorted(expected_records - seen_records)
        raise ValueError(f"locator/baseline record set mismatch: {missing_records[:3]}")
    if not documents:
        raise ValueError("no eligible locator documents found")
    return tuple(documents)


def _product_id_for_scope(product_scope: str) -> str | None:
    for label, product_id in PRODUCT_IDS.items():
        if label in product_scope:
            return product_id
    return None


def _scope_for_row(row: dict[str, Any]) -> ObjectScope | None:
    """Convert a benchmark turn target to the canonical internal scope."""
    if row.get("store_id") != STORE_ID:
        return None
    product_id = str(row.get("product_id") or "")
    if product_id not in PRODUCT_IDS.values():
        product_id = _product_id_for_scope(str(row.get("product_scope", ""))) or ""
    if product_id not in PRODUCT_IDS.values():
        return None
    variant_id = row.get("variant_id")
    if variant_id is not None and VARIANT_IDS.get(product_id) != variant_id:
        return None
    return ObjectScope(
        store_id=STORE_ID,
        product_id=product_id,
        variant_id=variant_id,
    )


def _candidate_matches_scope(candidate: Any, scope: ObjectScope) -> bool:
    if candidate.store_id != scope.store_id or candidate.product_id != scope.product_id:
        return False
    return (
        scope.variant_id is None
        and candidate.variant_id is None
        or (
            scope.variant_id is not None
            and candidate.variant_id in (None, scope.variant_id)
        )
    )


def _first_gold_rank(
    result: Any, source_id: str | None, gold_pages: list[int]
) -> int | None:
    if source_id is None or not gold_pages:
        return None
    for candidate in result.candidates:
        if candidate.source_id == source_id and candidate.page_number in gold_pages:
            return candidate.rank
    return None


def _wilson(successes: int, total: int) -> list[float] | None:
    if total == 0:
        return None
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denominator
    return [round(max(0.0, center - margin), 6), round(min(1.0, center + margin), 6)]


def evaluate(
    golden_dir: Path, locator_dir: Path, overlay_path: Path, chunk_manifest: Path
) -> dict[str, Any]:
    golden_manifest = _load_json(golden_dir / "manifest.json")
    query_path = golden_dir / "queries.annotated.jsonl"
    query_sha256 = _sha256(query_path)
    expected_query_file = golden_manifest["files"]["queries.annotated.jsonl"]
    if expected_query_file["sha256"] != query_sha256:
        raise ValueError("golden query file checksum mismatch")
    rows = _load_jsonl(query_path)
    if len(rows) != golden_manifest["query_count"]:
        raise ValueError("golden query count mismatch")
    for row in rows:
        expected_hash = (
            "sha256:" + hashlib.sha256(str(row["query_text"]).encode()).hexdigest()
        )
        if row.get("query_text_hash") != expected_hash:
            raise ValueError(f"golden query hash mismatch: {row.get('query_id')}")
        if row.get("dataset_version") != golden_manifest["dataset_version"]:
            raise ValueError(f"golden query dataset mismatch: {row.get('query_id')}")
    chunk_validation = validate_corrected_chunk_baseline_manifest(chunk_manifest)
    if not chunk_validation.accepted or chunk_validation.manifest is None:
        raise ValueError(
            f"corrected chunk baseline rejected: {chunk_validation.stop_reason.value}"
        )
    chunk_payload = chunk_validation.manifest
    locator_digests = [
        (path.name, _sha256(path)) for path in sorted(locator_dir.glob("*.jsonl"))
    ]
    corpus_identity = hashlib.sha256(
        json.dumps(
            {
                "chunk_manifest_sha256": _sha256(chunk_manifest),
                "locator_digests": locator_digests,
                "overlay_sha256": _sha256(overlay_path),
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    index_version = f"{chunk_payload.corpus_version}:{corpus_identity}"
    index = Bm25Index(
        _build_documents(locator_dir, overlay_path, chunk_payload),
        index_version=index_version,
    )

    evaluated: list[dict[str, Any]] = []
    answerable_total = 0
    answerable_hits = 0
    answerable_top5 = 0
    reciprocal_ranks: list[float] = []
    ndcg_values: list[float] = []
    abstention_total = 0
    abstention_correct = 0
    scope_leakage = 0
    stop_reasons: Counter[str] = Counter()
    latencies: list[float] = []

    for row in rows:
        if row["static_eval_eligibility"] != "gold_page_annotated":
            continue
        scope = _scope_for_row(row)
        if scope is None:
            evaluated.append(
                {
                    "query_id": row["query_id"],
                    "query_text_hash": row["query_text_hash"],
                    "evaluation_status": "UNSUPPORTED_MULTI_PRODUCT_SCOPE",
                    "expected_route": row["expected_route"],
                }
            )
            continue
        started = time.perf_counter()
        result = index.search(
            Bm25Request(
                turn_target=scope,
                query=row["query_text"],
                k=10,
            )
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        latencies.append(elapsed_ms)
        if result.stop_reason is not None:
            stop_reasons[result.stop_reason.value] += 1
        if any(
            not _candidate_matches_scope(candidate, scope)
            for candidate in result.candidates
        ):
            scope_leakage += 1
        source_id = row.get("gold_source_id")
        gold_pages = row.get("gold_pages", [])
        rank = _first_gold_rank(result, source_id, gold_pages)
        expected_answer = row["expected_route"] == "answer" and bool(gold_pages)
        if expected_answer:
            answerable_total += 1
            if rank is not None:
                answerable_hits += 1
                answerable_top5 += rank <= 5
                reciprocal_ranks.append(1 / rank)
                gains = [
                    1 if candidate.rank == rank else 0
                    for candidate in result.candidates
                ]
                dcg = sum(
                    gain / math.log2(index + 2) for index, gain in enumerate(gains[:10])
                )
                idcg = 1.0
                ndcg_values.append(dcg / idcg)
        else:
            abstention_total += 1
            abstention_correct += int(not result.candidates)
        evaluated.append(
            {
                "query_id": row["query_id"],
                "query_text_hash": row["query_text_hash"],
                "evaluation_status": "EVALUATED",
                "expected_route": row["expected_route"],
                "gold_source_id": source_id,
                "gold_pages": gold_pages,
                "first_gold_rank": rank,
                "returned_pages": [
                    {
                        "source_id": c.source_id,
                        "page_number": c.page_number,
                        "rank": c.rank,
                        "store_id": c.store_id,
                        "product_id": c.product_id,
                        "variant_id": c.variant_id,
                    }
                    for c in result.candidates
                ],
                "stop_reason": result.stop_reason.value if result.stop_reason else None,
                "filtered_out_count": result.filtered_out_count,
                "retrieval_tokens_used": result.retrieval_tokens_used,
                "latency_ms": round(elapsed_ms, 3),
            }
        )

    evaluated_count = sum(
        item["evaluation_status"] == "EVALUATED" for item in evaluated
    )
    result = {
        "schema_version": "bm25-baseline-evaluation.v0.1",
        "status": "EXECUTED_OFFLINE_METADATA_ONLY",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "golden_set": {
            "dataset_version": golden_manifest["dataset_version"],
            "manifest_sha256": _sha256(golden_dir / "manifest.json"),
            "query_file_sha256": query_sha256,
            "query_count": golden_manifest["query_count"],
            "evaluated_page_annotated_count": evaluated_count,
        },
        "corpus": {
            "index_version": index_version,
            "document_count": index.document_count,
            "locator_dir": str(locator_dir),
            "overlay_path": str(overlay_path),
            "chunk_manifest_sha256": _sha256(chunk_manifest),
            "locator_file_sha256": dict(locator_digests),
            "overlay_sha256": _sha256(overlay_path),
        },
        "method": {
            "name": "in-memory BM25",
            "k1": 1.2,
            "b": 0.75,
            "scope_filter_before_score": True,
            "network": "disabled",
            "external_model_calls": 0,
            "shopify_reads": 0,
            "shopify_writes": 0,
            "candidate_cap": 10,
            "max_retrieval_tokens": 4000,
            "turn_deadline_ms": 8000,
            "token_estimate_policy": "tokenizer_count_per_page",
            "budget_selection_policy": (
                "ranked candidates are added in order until k or the "
                "retrieval-token budget"
            ),
        },
        "metrics": {
            "answerable_count": answerable_total,
            "evidence_recall_at_5": answerable_top5 / answerable_total
            if answerable_total
            else None,
            "evidence_recall_at_10": answerable_hits / answerable_total
            if answerable_total
            else None,
            "evidence_recall_at_10_ci95": _wilson(answerable_hits, answerable_total),
            "mrr": sum(reciprocal_ranks) / len(reciprocal_ranks)
            if reciprocal_ranks
            else None,
            "ndcg_at_10": sum(ndcg_values) / len(ndcg_values) if ndcg_values else None,
            "answer_correctness_proxy": answerable_hits / answerable_total
            if answerable_total
            else None,
            "abstention_total": abstention_total,
            "abstention_correctness": abstention_correct / abstention_total
            if abstention_total
            else None,
            "scope_leakage_count": scope_leakage,
            "unit_request_cost": {
                "external_provider_cost": 0.0,
                "currency": "N/A",
                "network_calls": 0,
            },
            "p50_latency_ms": round(sorted(latencies)[len(latencies) // 2], 3)
            if latencies
            else None,
            "p95_latency_ms": round(
                sorted(latencies)[
                    min(len(latencies) - 1, math.ceil(len(latencies) * 0.95) - 1)
                ],
                3,
            )
            if latencies
            else None,
        },
        "stop_reasons": dict(sorted(stop_reasons.items())),
        "confidence_interval_method": (
            "Wilson 95% for binary recall; paired CI/net-benefit comparison is "
            "not applicable to the single BM25 arm."
        ),
        "limitations": [
            "This is an expert benchmark, not real-user satisfaction evidence.",
            "The 36 coverage-only rows are not included in page-level evidence recall.",
            "No Hybrid/Reranker replacement decision is made by this report.",
            "Source text was read in memory only and is absent from this report.",
        ],
        "per_query": evaluated,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden-dir", type=Path, required=True)
    parser.add_argument("--locator-dir", type=Path, required=True)
    parser.add_argument("--overlay", type=Path, required=True)
    parser.add_argument("--chunk-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise SystemExit("append-only refusal: output directory contains files")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = evaluate(
        args.golden_dir, args.locator_dir, args.overlay, args.chunk_manifest
    )
    report_path = args.output_dir / "evaluation_report.json"
    _write_json(report_path, report)
    files = {
        "evaluation_report.json": {
            "bytes": report_path.stat().st_size,
            "sha256": _sha256(report_path),
        }
    }
    checksums = {
        "schema_version": "checksums.v0.1",
        "dataset_version": "bm25-baseline-evaluation-20260907-v0.1",
        "files": files,
        "self_reference_policy": "This sidecar excludes its own sha256.",
    }
    _write_json(args.output_dir / "checksums.json", checksums)
    print(
        json.dumps(
            {
                "status": report["status"],
                "output_dir": str(args.output_dir),
                "index_version": report["corpus"]["index_version"],
                "document_count": report["corpus"]["document_count"],
                "answerable_count": report["metrics"]["answerable_count"],
                "recall_at_10": report["metrics"]["evidence_recall_at_10"],
                "scope_leakage_count": report["metrics"]["scope_leakage_count"],
                "shopify_reads": report["method"]["shopify_reads"],
                "shopify_writes": report["method"]["shopify_writes"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
