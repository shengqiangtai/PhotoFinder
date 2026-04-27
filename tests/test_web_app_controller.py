import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "tests" / "web_app_controller_harness.js"


class WebAppControllerTests(unittest.TestCase):
    def _run_scenario(self, scenario: str) -> None:
        completed = subprocess.run(
            ["node", str(HARNESS), scenario],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            self.fail(completed.stderr or completed.stdout or f"Scenario {scenario} failed")

    def test_bootstrap_populates_shell_mounts(self) -> None:
        self._run_scenario("bootstrap")

    def test_drawer_compacts_long_folder_paths(self) -> None:
        self._run_scenario("folder-path-display")

    def test_bootstrap_failure_renders_fatal_state(self) -> None:
        self._run_scenario("bootstrap-failure")

    def test_bootstrap_starts_polling_for_active_jobs(self) -> None:
        self._run_scenario("bootstrap-polling")

    def test_open_folder_picker_refreshes_drawer_and_starts_index_polling(self) -> None:
        self._run_scenario("open-folder")

    def test_open_folder_failure_stays_local_to_the_drawer(self) -> None:
        self._run_scenario("open-folder-failure")

    def test_polling_guard_skips_overlapping_status_ticks(self) -> None:
        self._run_scenario("polling-guard")

    def test_polling_error_clears_timer_and_surfaces_message(self) -> None:
        self._run_scenario("polling-error")

    def test_search_submit_renders_rewritten_query_and_selection(self) -> None:
        self._run_scenario("search-submit")

    def test_search_with_no_matches_renders_empty_result_state(self) -> None:
        self._run_scenario("no-search-matches")

    def test_stale_search_results_do_not_overwrite_latest_query(self) -> None:
        self._run_scenario("stale-search")


if __name__ == "__main__":
    unittest.main()
