from __future__ import annotations

import inspect
import re
from typing import Any, List, Optional

import numpy as np
import sqlite_vec

import config
from utils.query_rewriter import contains_cjk, rewrite_query_for_clip


def _distance_to_similarity(distance: float) -> float:
    similarity = 1.0 - (distance / 2.0)
    if similarity < 0.0:
        return 0.0
    if similarity > 1.0:
        return 1.0
    return round(similarity, 4)


def _query_terms(query: str) -> list[str]:
    terms = re.findall(r"[\w\u3400-\u9fff]+", query.lower())
    return [term for term in terms if len(term) >= 2]


def _keyword_score(query: str, *, filename: str, path: str | None = None) -> float:
    terms = _query_terms(query)
    if not terms:
        return 0.0
    filename_text = (filename or "").lower()
    path_text = (path or "").lower()
    score = 0.0
    for term in terms:
        if term in filename_text:
            score += 1.0
        elif term in path_text:
            score += 0.8
    return min(1.0, score / len(terms))


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


def compute_match_scores(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not results:
        return []

    similarities = [float(result.get("similarity", 0.0)) for result in results]
    min_similarity = min(similarities)
    max_similarity = max(similarities)
    similarity_range = max_similarity - min_similarity
    confidence_cap = 100 if similarity_range >= 0.05 else 65
    if similarity_range <= 0.000001:
        normalized_scores = [0.5 for _ in similarities]
    else:
        normalized_scores = [(similarity - min_similarity) / similarity_range for similarity in similarities]

    scored_results: list[dict[str, Any]] = []
    for result, normalized_score in zip(results, normalized_scores):
        keyword_score = float(result.get("keyword_score", 0.0))
        blended = (0.8 * normalized_score) + (0.2 * keyword_score)
        match_score = int(round(blended * confidence_cap))
        scored_results.append(
            {
                **result,
                "match_score": max(0, min(100, match_score)),
            }
        )
    return sorted(scored_results, key=lambda item: item["match_score"], reverse=True)


def expand_query_variants(query: str, *, text_model: str | None = None) -> list[str]:
    normalized = " ".join(query.split())
    if not normalized:
        return []
    if text_model in {"multilingual", "api"} and contains_cjk(normalized):
        return [normalized]

    variants: list[str] = []

    def add_variant(value: str) -> None:
        value = " ".join(value.split())
        if value and value not in variants:
            variants.append(value)

    add_variant(normalized)
    rewritten = rewrite_query_for_clip(normalized)
    template_base = rewritten.rewritten_query if rewritten.was_rewritten else normalized

    if contains_cjk(normalized) and rewritten.was_rewritten:
        add_variant(rewritten.rewritten_query)

    add_variant(f"a photo of {template_base}")
    add_variant(f"an image of {template_base}")
    return variants


def _build_filter_sql(
    *,
    folder_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> tuple[str, list[Any]]:
    clauses = ["p.has_vector = 1"]
    filter_params: list[Any] = []

    if folder_id is not None:
        clauses.append("p.folder_id = ?")
        filter_params.append(folder_id)
    if date_from is not None:
        clauses.append("date(p.taken_at) >= date(?)")
        filter_params.append(date_from)
    if date_to is not None:
        clauses.append("date(p.taken_at) <= date(?)")
        filter_params.append(date_to)

    return " AND ".join(clauses), filter_params


async def _encode_query_blob(query: str, *, embedder) -> bytes:
    query_vector = await _maybe_await(embedder.encode_text(query))
    query_vector = np.asarray(query_vector, dtype=np.float32).reshape(-1)
    expected_dim = int(getattr(embedder, "vector_dim", config.VECTOR_DIM))
    if query_vector.shape[0] != expected_dim:
        raise RuntimeError(
            f"Text encoder output dimension mismatch: expected {expected_dim}, got {query_vector.shape[0]}"
        )
    return sqlite_vec.serialize_float32(np.asarray(query_vector, dtype=np.float32).tolist())


def _row_to_search_result(row: Any, *, include_distance: bool = False) -> dict[str, Any]:
    result = {
        "id": row["id"],
        "filename": row["filename"],
        "taken_at": row["taken_at"],
        "path": row["path"],
        "thumbnail_url": f"/api/thumbnail/{row['id']}",
        "full_image_url": f"/api/image/{row['id']}",
        "similarity": _distance_to_similarity(row["distance"]),
    }
    if include_distance:
        result["distance"] = round(float(row["distance"]), 6)
    return result


async def _search_variants(
    query: str,
    *,
    top_k: int = config.DEFAULT_TOP_K,
    folder_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    database,
    embedder,
    include_distance: bool = False,
) -> list[dict[str, Any]]:
    where_sql, filter_params = _build_filter_sql(folder_id=folder_id, date_from=date_from, date_to=date_to)
    sql = f"""
        SELECT
            p.id,
            p.filename,
            p.path,
            p.taken_at,
            vec_distance_l2(v.embedding, ?) AS distance
        FROM photo_vectors v
        JOIN photos p ON p.id = v.photo_id
        WHERE {where_sql}
        ORDER BY distance ASC
        LIMIT ?
    """

    text_model = "api" if getattr(embedder, "provider", None) in {"jina", "voyage"} else getattr(embedder, "loaded_text_model", None)
    variant_payloads: list[dict[str, Any]] = []
    async with database.connect() as connection:
        for query_variant in expand_query_variants(query, text_model=text_model):
            query_blob = await _encode_query_blob(query_variant, embedder=embedder)
            params: list[Any] = [query_blob, *filter_params, top_k]
            cursor = await connection.execute(sql, tuple(params))
            rows = await cursor.fetchall()
            variant_results = []
            for row in rows:
                result = _row_to_search_result(row, include_distance=include_distance)
                result["keyword_score"] = _keyword_score(query_variant, filename=row["filename"], path=row["path"])
                variant_results.append(result)
            variant_results = compute_match_scores(variant_results)
            variant_payloads.append({"query": query_variant, "results": variant_results})

    return variant_payloads


async def search(
    query: str,
    *,
    top_k: int = config.DEFAULT_TOP_K,
    folder_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    database,
    embedder,
) -> List[dict[str, Any]]:
    variants = await _search_variants(
        query,
        top_k=top_k,
        folder_id=folder_id,
        date_from=date_from,
        date_to=date_to,
        database=database,
        embedder=embedder,
    )
    best_results: dict[int, dict[str, Any]] = {}
    for variant in variants:
        for result in variant["results"]:
            existing = best_results.get(result["id"])
            if existing is not None and existing["match_score"] >= result["match_score"]:
                continue
            best_results[result["id"]] = result
    return sorted(best_results.values(), key=lambda item: item["match_score"], reverse=True)[:top_k]


async def debug_search(
    query: str,
    *,
    top_k: int = config.DEFAULT_TOP_K,
    folder_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    database,
    embedder,
) -> dict[str, Any]:
    text_model = "api" if getattr(embedder, "provider", None) in {"jina", "voyage"} else getattr(embedder, "loaded_text_model", None)
    variants = await _search_variants(
        query,
        top_k=top_k,
        folder_id=folder_id,
        date_from=date_from,
        date_to=date_to,
        database=database,
        embedder=embedder,
        include_distance=True,
    )
    return {
        "text_model": text_model,
        "variants": variants,
    }
