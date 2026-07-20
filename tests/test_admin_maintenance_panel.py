import os
import unittest

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("ADMIN_ID", "1")

from database import db_core
from handlers import admin_handlers


class MaintenancePanelTests(unittest.TestCase):
    def test_maintenance_menu_text_contains_status_and_exception_count(self) -> None:
        text = admin_handlers.build_maintenance_menu_text(enabled=True, allowed_users=[101, 202])

        self.assertIn("Техработы: ВКЛЮЧЕНЫ", text)
        self.assertIn("Исключений: 2", text)

    def test_admin_handlers_use_shared_database_path(self) -> None:
        self.assertEqual(admin_handlers.DB_PATH, db_core.DB_PATH)


if __name__ == "__main__":
    unittest.main()
