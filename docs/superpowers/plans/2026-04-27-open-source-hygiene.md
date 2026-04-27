# Open Source Hygiene Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prepare PhotoFinder for a clean public GitHub repository without publishing private local files, generated artifacts, or credentials.

**Architecture:** Keep the source tree intact and add repository-level guardrails. Treat distributable binaries as GitHub Release artifacts, not Git-tracked files.

**Tech Stack:** Python, FastAPI, SQLite, ONNX Runtime, PyInstaller, browser-based frontend, unittest.

---

### Task 1: Repository Hygiene Tests

**Files:**
- Create: `tests/test_repository_hygiene.py`

- [ ] Add tests that require `.gitignore`, dependency metadata, and privacy documentation.
- [ ] Add a source scan that fails if public text files include the local username path.
- [ ] Run: `./.venv/bin/python -m unittest tests.test_repository_hygiene -v`

### Task 2: Open Source Metadata

**Files:**
- Create: `.gitignore`
- Create: `requirements.txt`
- Create: `LICENSE`
- Create: `CONTRIBUTING.md`
- Create: `SECURITY.md`
- Modify: `README.md`

- [ ] Ignore virtualenvs, Python caches, model files, databases, secrets, temporary files, and build/release outputs.
- [ ] Declare runtime and test dependencies.
- [ ] Document install, test, packaging, privacy, and release artifact policy.

### Task 3: Privacy Sanitization

**Files:**
- Modify: `docs/startup-flow.md`
- Modify: `PhotoFinder_架构文档.md`
- Modify: `tests/web_app_controller_harness.js`

- [ ] Replace local absolute paths with generic examples.
- [ ] Preserve tests that assert full local paths are not rendered in the UI.

### Task 4: Verification

- [ ] Run: `./.venv/bin/python -m unittest discover -v`
- [ ] Run a sensitive-text scan excluding ignored/generated directories.
- [ ] Report any remaining risks clearly.
