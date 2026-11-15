"""IPC worker unit smoke (no network required for hello/meta/config)."""
import json
import unittest
from unittest import mock

from core import ipc_worker


class IpcWorkerTests(unittest.TestCase):
    def test_hello(self):
        r = ipc_worker.handle("hello", {})
        self.assertIn("version", r)

    def test_meta_and_config(self):
        with mock.patch("core.ipc_worker.load_config", return_value={"symbol": "zs_jcj", "language": "zh"}):
            meta = ipc_worker.handle("meta", {})
        self.assertTrue(meta["symbols"])
        self.assertIn("widths", meta)

    def test_unknown(self):
        with self.assertRaises(ValueError):
            ipc_worker.handle("nope", {})


if __name__ == "__main__":
    unittest.main()
