from html.parser import HTMLParser
import re
import unittest

from fastapi.testclient import TestClient

from api.app import create_app


VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


class _ShellMarkupParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.id_counts = {}
        self.attrs_by_id = {}
        self.parent_by_id = {}
        self.stylesheet_links = []
        self.script_tags = []
        self.data_views = []
        self._open_elements = []

    def handle_starttag(self, tag: str, attrs) -> None:
        attributes = dict(attrs)
        parent_id = None
        for _, ancestor_id in reversed(self._open_elements):
            if ancestor_id:
                parent_id = ancestor_id
                break
        element_id = attributes.get("id")
        if element_id is not None:
            self.id_counts[element_id] = self.id_counts.get(element_id, 0) + 1
            self.attrs_by_id[element_id] = attributes
            self.parent_by_id[element_id] = parent_id
        if tag == "link":
            self.stylesheet_links.append(attributes)
        if tag == "script":
            self.script_tags.append(attributes)
        data_view = attributes.get("data-view")
        if data_view is not None:
            self.data_views.append(data_view)
        if tag not in VOID_TAGS:
            self._open_elements.append((tag, element_id))

    def handle_endtag(self, tag: str) -> None:
        while self._open_elements:
            current_tag, _ = self._open_elements.pop()
            if current_tag == tag:
                return


def _assert_descendant(parser: _ShellMarkupParser, child_id: str, ancestor_id: str) -> None:
    current_id = parser.parent_by_id.get(child_id)
    while current_id is not None:
        if current_id == ancestor_id:
            return
        current_id = parser.parent_by_id.get(current_id)
    raise AssertionError(f"{child_id!r} is not inside {ancestor_id!r}")


class _NoOpDatabase:
    async def initialize(self) -> None:
        return None


class BootstrapShellSmokeTests(unittest.TestCase):
    def test_static_index_serves_phase5_shell(self) -> None:
        with TestClient(create_app(database=_NoOpDatabase())) as client:
            response = client.get("/web/index.html")
            parser = _ShellMarkupParser()
            parser.feed(response.text)
        required_ids = {
            "photofinder-app",
            "left-drawer",
            "drawer-body",
            "library-card",
            "models-card",
            "indexing-card",
            "device-card",
            "folder-list",
            "center-stage",
            "detail-panel",
            "drawer-nav",
            "stage-content",
            "detail-body",
            "stage-title",
            "stage-subtitle",
            "detail-title",
            "detail-subtitle",
        }

        self.assertEqual(response.status_code, 200)
        for element_id in required_ids:
            self.assertEqual(parser.id_counts.get(element_id), 1)
        _assert_descendant(parser, "stage-content", "center-stage")
        _assert_descendant(parser, "detail-body", "detail-panel")
        self.assertTrue(
            any(link.get("href", "").startswith("/web/style.css") and link.get("rel") == "stylesheet" for link in parser.stylesheet_links)
        )
        self.assertTrue(
            any(script.get("src", "").startswith("/web/app.js") for script in parser.script_tags)
        )
        self.assertGreaterEqual(len(parser.data_views), 1)

    def test_static_style_serves_phase5_stylesheet(self) -> None:
        with TestClient(create_app(database=_NoOpDatabase())) as client:
            response = client.get("/web/style.css")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/css"))
        self.assertTrue(response.text.strip())
        self.assertNotIn("<html", response.text.lower())

    def test_static_app_serves_bootstrap_controller(self) -> None:
        with TestClient(create_app(database=_NoOpDatabase())) as client:
            response = client.get("/web/app.js")

        self.assertEqual(response.status_code, 200)
        self.assertIn("javascript", response.headers["content-type"])
        self.assertTrue(response.text.strip())
        self.assertNotIn("<html", response.text.lower())

    def test_root_redirects_to_web_index(self) -> None:
        with TestClient(create_app(database=_NoOpDatabase())) as client:
            response = client.get("/", follow_redirects=False)

        self.assertEqual(response.status_code, 307)
        self.assertEqual(response.headers["location"], "/web/index.html")


if __name__ == "__main__":
    unittest.main()
