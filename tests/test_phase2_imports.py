import unittest


class Phase2ImportSmokeTests(unittest.TestCase):
    def test_phase2_modules_import_and_app_builds(self) -> None:
        import api.routes.library  # noqa: F401
        import api.routes.system  # noqa: F401
        import core.scanner  # noqa: F401
        import utils.image_utils  # noqa: F401

        from api.app import create_app

        app = create_app()

        self.assertIsNotNone(app)


if __name__ == "__main__":
    unittest.main()
