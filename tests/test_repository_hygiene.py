import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class RepositoryHygieneTests(unittest.TestCase):
    def test_open_source_metadata_exists(self) -> None:
        required_files = [
            ".gitignore",
            "requirements.txt",
            "LICENSE",
            "CONTRIBUTING.md",
            "SECURITY.md",
        ]

        for relative_path in required_files:
            with self.subTest(path=relative_path):
                self.assertTrue((ROOT / relative_path).exists())

    def test_gitignore_excludes_private_and_generated_files(self) -> None:
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        required_patterns = [
            ".venv/",
            ".venv.*/",
            "__pycache__/",
            ".pytest_cache/",
            ".DS_Store",
            ".env",
            "*.db",
            "*.sqlite",
            "*.sqlite3",
            "*.onnx",
            "*.safetensors",
            "models/*",
            "!models/.gitkeep",
            "tmp/",
            "dist/",
            "release/",
            "build/*/",
            "*.zip",
            "*.pkg",
        ]

        for pattern in required_patterns:
            with self.subTest(pattern=pattern):
                self.assertIn(pattern, gitignore)

    def test_public_docs_do_not_include_local_user_paths(self) -> None:
        ignored_roots = {
            ".venv",
            ".venv.conda-loadext-crash",
            ".venv.py38-noext-stable-backup",
            ".pytest_cache",
            "__pycache__",
            "build",
            "dist",
            "release",
            "tmp",
        }
        text_suffixes = {".md", ".py", ".js", ".html", ".css", ".txt", ".spec"}
        offenders = []

        for path in ROOT.rglob("*"):
            if not path.is_file() or path.suffix not in text_suffixes:
                continue
            if any(part in ignored_roots for part in path.relative_to(ROOT).parts):
                continue
            content = path.read_text(encoding="utf-8", errors="ignore")
            local_user_path = "/Users/" + "sheng" + "qiangtai"
            if local_user_path in content:
                offenders.append(str(path.relative_to(ROOT)))

        self.assertEqual([], offenders)

    def test_readme_documents_privacy_and_release_policy(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("隐私与本地数据", readme)
        self.assertIn("GitHub Releases", readme)
        self.assertIn("python -m unittest discover -v", readme)


if __name__ == "__main__":
    unittest.main()
