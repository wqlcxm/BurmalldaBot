import asyncio
import os
import tempfile
import unittest

from database import db_core


class MaintenanceModeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "memes.db")
        self.original_db_path = db_core.DB_PATH
        db_core.DB_PATH = self.db_path
        asyncio.run(db_core.init_db(self.db_path))

    def tearDown(self) -> None:
        db_core.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_maintenance_mode_and_allowed_users(self) -> None:
        asyncio.run(db_core.set_maintenance_mode(True))
        self.assertTrue(asyncio.run(db_core.is_maintenance_enabled()))

        asyncio.run(db_core.add_allowed_user(101))
        asyncio.run(db_core.add_allowed_user(202))

        self.assertTrue(asyncio.run(db_core.is_user_allowed(101)))
        self.assertTrue(asyncio.run(db_core.is_user_allowed(202)))
        self.assertFalse(asyncio.run(db_core.is_user_allowed(303)))

        asyncio.run(db_core.remove_allowed_user(101))
        self.assertFalse(asyncio.run(db_core.is_user_allowed(101)))

        asyncio.run(db_core.set_maintenance_mode(False))
        self.assertFalse(asyncio.run(db_core.is_maintenance_enabled()))


if __name__ == "__main__":
    unittest.main()
