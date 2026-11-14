import tempfile
import unittest
from pathlib import Path

from api.request_limits import take_slot
from auth.schemas import RegisterRequest
from pydantic import ValidationError


class SecurityTests(unittest.TestCase):
    def test_password_policy(self):
        for password in ("short1!A", "lowercase123!", "UPPERCASE123!", "NoDigitsHere!", "NoSpecial1234"):
            with self.assertRaises(ValidationError):
                RegisterRequest(email="test@example.com", password=password)
        self.assertTrue(RegisterRequest(email="test@example.com", password="StrongExample123!"))

    def test_persistent_quota_and_expiry(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "limits.db"
            self.assertEqual(take_slot(db, "client", "auth", 2, 60, 120), 0)
            self.assertEqual(take_slot(db, "client", "auth", 2, 60, 121), 0)
            self.assertEqual(take_slot(db, "client", "auth", 2, 60, 122), 58)
            self.assertEqual(take_slot(db, "other", "auth", 2, 60, 122), 0)
            self.assertEqual(take_slot(db, "client", "upload", 2, 60, 122), 0)
            self.assertEqual(take_slot(db, "client", "auth", 2, 60, 180), 0)


if __name__ == "__main__":
    unittest.main()
