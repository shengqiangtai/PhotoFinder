# Chinese Query Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Chinese search queries usable without rebuilding the current CLIP-based image index by rewriting Chinese visual terms into English retrieval prompts.

**Architecture:** Keep the current indexed vectors unchanged. Add one lightweight query rewrite module that detects Chinese input and rewrites it into an English prompt via a curated visual-term lexicon, then thread the rewritten query through the existing search route while preserving the original user query in the API response.

**Tech Stack:** FastAPI, unittest, existing CLIP text search path.

---

### Task 1: Lock rewrite behavior with tests

**Files:**
- Create: `tests/test_query_rewriter.py`
- Modify: `tests/test_search_routes.py`
- Modify: `tests/test_schemas.py`

- [ ] Add failing tests for Chinese detection and lexicon-based rewrite output.
- [ ] Add failing route test proving Chinese queries pass a rewritten English prompt into `core.searcher.search`.
- [ ] Add failing schema test for `rewritten_query` in search responses.

### Task 2: Implement query rewrite module

**Files:**
- Create: `utils/query_rewriter.py`

- [ ] Implement `contains_cjk()` and `rewrite_query_for_clip()`.
- [ ] Add a small curated Chinese-to-English visual lexicon.
- [ ] Return both original and rewritten query so route logic can stay simple.

### Task 3: Integrate rewrite into search API

**Files:**
- Modify: `api/schemas.py`
- Modify: `api/routes/search.py`

- [ ] Extend `SearchResponse` with optional `rewritten_query`.
- [ ] Run rewrite before calling `core.searcher.search`.
- [ ] Preserve original query in `query`, return rewritten prompt in `rewritten_query`.

### Task 4: Verify end-to-end Chinese search

**Files:**
- Verify only

- [ ] Run focused rewrite/search tests, then the full suite.
- [ ] Start `python3 main.py` and verify a real Chinese query like `日落` returns indexed results.
