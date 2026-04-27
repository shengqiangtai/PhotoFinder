import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class Phase6ArtifactTests(unittest.TestCase):
    def test_build_specs_exist_for_three_platforms(self) -> None:
        build_dir = ROOT / "build"
        expected_specs = {
            "build_windows.spec",
            "build_mac.spec",
            "build_linux.spec",
        }

        self.assertTrue(build_dir.exists())
        self.assertTrue((ROOT / "models" / ".gitkeep").exists())

        for name in expected_specs:
            spec_path = build_dir / name
            self.assertTrue(spec_path.exists(), msg=f"missing {name}")
            content = spec_path.read_text(encoding="utf-8")
            self.assertIn("PhotoFinder", content)
            self.assertIn("web", content)
            self.assertIn("main.py", content)

    def test_readme_contains_release_sections(self) -> None:
        readme = ROOT / "README.md"
        self.assertTrue(readme.exists())

        content = readme.read_text(encoding="utf-8")
        self.assertIn("# PhotoFinder", content)
        self.assertIn("打包发布（Phase 6）", content)
        self.assertIn("build/build_windows.spec", content)
        self.assertIn("下载链接", content)
        self.assertIn("常见问题", content)


if __name__ == "__main__":
    unittest.main()
