import unittest
from unittest import mock

from utils.network_utils import get_lan_ip


class NetworkUtilsTests(unittest.TestCase):
    def test_get_lan_ip_returns_none_when_socket_connect_fails(self) -> None:
        with mock.patch("socket.socket.connect", side_effect=OSError("no network")):
            self.assertIsNone(get_lan_ip())


if __name__ == "__main__":
    unittest.main()
