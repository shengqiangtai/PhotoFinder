import unittest

from pydantic import ValidationError


class SchemaTests(unittest.TestCase):
    def test_add_folder_request_creates_and_serializes(self) -> None:
        from api.schemas import AddFolderRequest

        payload = AddFolderRequest(path="/tmp/photos")

        self.assertEqual(payload.path, "/tmp/photos")
        self.assertEqual(payload.model_dump(), {"path": "/tmp/photos"})

    def test_folder_response_creates_and_serializes(self) -> None:
        from api.schemas import FolderResponse

        payload = FolderResponse(
            id=1,
            path="/tmp/photos",
            photo_count=10,
            indexed_count=3,
            last_scan=None,
        )

        self.assertEqual(payload.id, 1)
        self.assertEqual(
            payload.model_dump(),
            {
                "id": 1,
                "path": "/tmp/photos",
                "photo_count": 10,
                "indexed_count": 3,
                "last_scan": None,
            },
        )

    def test_add_folder_response_creates_and_serializes(self) -> None:
        from api.schemas import AddFolderResponse

        payload = AddFolderResponse(folder_id=7, path="/tmp/photos", status="scanning_started")

        self.assertEqual(payload.folder_id, 7)
        self.assertEqual(
            payload.model_dump(),
            {
                "folder_id": 7,
                "path": "/tmp/photos",
                "status": "scanning_started",
            },
        )

    def test_folder_list_response_serializes_nested_folders(self) -> None:
        from api.schemas import FolderListResponse, FolderResponse

        payload = FolderListResponse(
            folders=[
                FolderResponse(
                    id=1,
                    path="/tmp/photos",
                    photo_count=10,
                    indexed_count=3,
                    last_scan=None,
                )
            ]
        )

        self.assertEqual(
            payload.model_dump(),
            {
                "folders": [
                    {
                        "id": 1,
                        "path": "/tmp/photos",
                        "photo_count": 10,
                        "indexed_count": 3,
                        "last_scan": None,
                    }
                ]
            },
        )

    def test_system_info_response_serializes_structured_status(self) -> None:
        from api.schemas import DownloadProgressResponse, ModelStatusResponse, SystemInfoResponse

        payload = SystemInfoResponse(
            version="1.0.0",
            model_status=ModelStatusResponse(
                visual="loaded",
                textual="downloading",
                multilingual="not_downloaded",
            ),
            download_progress=DownloadProgressResponse(model="clip_visual", percent=45),
            total_photos=52341,
            indexed_photos=48200,
            db_size_mb=312.5,
            lan_url="http://192.168.1.5:7700",
            first_run=False,
        )

        self.assertEqual(
            payload.model_dump(),
            {
                "version": "1.0.0",
                "model_status": {
                    "visual": "loaded",
                    "textual": "downloading",
                    "multilingual": "not_downloaded",
                },
                "download_progress": {"model": "clip_visual", "percent": 45},
                "total_photos": 52341,
                "indexed_photos": 48200,
                "db_size_mb": 312.5,
                "lan_url": "http://192.168.1.5:7700",
                "first_run": False,
            },
        )

    def test_system_info_response_supports_null_optional_fields(self) -> None:
        from api.schemas import ModelStatusResponse, SystemInfoResponse

        payload = SystemInfoResponse(
            version="1.0.0",
            model_status=ModelStatusResponse(
                visual="not_downloaded",
                textual="not_downloaded",
                multilingual="not_downloaded",
            ),
            download_progress=None,
            total_photos=0,
            indexed_photos=0,
            db_size_mb=0.0,
            lan_url=None,
            first_run=True,
        )

        self.assertEqual(
            payload.model_dump(),
            {
                "version": "1.0.0",
                "model_status": {
                    "visual": "not_downloaded",
                    "textual": "not_downloaded",
                    "multilingual": "not_downloaded",
                },
                "download_progress": None,
                "total_photos": 0,
                "indexed_photos": 0,
                "db_size_mb": 0.0,
                "lan_url": None,
                "first_run": True,
            },
        )

    def test_open_folder_response_accepts_exactly_one_outcome(self) -> None:
        from api.schemas import OpenFolderResponse

        self.assertEqual(
            OpenFolderResponse(selected_path="/tmp/photos").model_dump(),
            {"selected_path": "/tmp/photos", "cancelled": None},
        )
        self.assertEqual(
            OpenFolderResponse(cancelled=True).model_dump(),
            {"selected_path": None, "cancelled": True},
        )

    def test_open_folder_response_rejects_ambiguous_or_missing_outcomes(self) -> None:
        from api.schemas import OpenFolderResponse

        with self.assertRaises(ValidationError):
            OpenFolderResponse()

        with self.assertRaises(ValidationError):
            OpenFolderResponse(selected_path="/tmp/photos", cancelled=True)

        with self.assertRaises(ValidationError):
            OpenFolderResponse(cancelled=False)

    def test_search_response_serializes_results(self) -> None:
        from api.schemas import SearchResponse, SearchResultResponse

        response = SearchResponse(
            results=[
                SearchResultResponse(
                    id=1,
                    filename="sunset.jpg",
                    taken_at="2024-04-10T10:00:00",
                    thumbnail_url="/api/thumbnail/1",
                    full_image_url="/api/image/1",
                    similarity=0.87,
                    match_score=91,
                )
            ],
            total=1,
            query="sunset",
            rewritten_query="sunset",
            search_time_ms=12,
        )

        self.assertEqual(
            response.model_dump(),
            {
                "results": [
                    {
                        "id": 1,
                        "filename": "sunset.jpg",
                        "taken_at": "2024-04-10T10:00:00",
                        "thumbnail_url": "/api/thumbnail/1",
                        "full_image_url": "/api/image/1",
                        "similarity": 0.87,
                        "match_score": 91,
                    }
                ],
                "total": 1,
                "query": "sunset",
                "rewritten_query": "sunset",
                "search_time_ms": 12,
            },
        )


if __name__ == "__main__":
    unittest.main()
