"""Budgets de décompression et de rendu des fichiers."""

import io
import os
import unittest
import zipfile
from types import SimpleNamespace

os.environ.update({
    "ENVIRONMENT": "production",
    "MONGO_URL": "mongodb://127.0.0.1:27017",
    "DB_NAME": "kylot_file_bounds_test",
    "JWT_SECRET": "file-bounds-secret-at-least-32-characters",
    "FRONTEND_URL": "https://app.example.invalid",
    "CORS_ORIGINS": "https://app.example.invalid",
    "ALLOW_PUBLIC_REGISTRATION": "false",
    "ALLOW_DEMO_DATA": "false",
    "ALLOW_TOKEN_RESPONSE": "false",
    "RUN_STARTUP_MIGRATIONS": "false",
    "EXPOSE_API_DOCS": "false",
    "COOKIE_SECURE": "true",
    "COOKIE_SAMESITE": "lax",
})

from fastapi import HTTPException
from backend import server


def zip_with_entries(count: int) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as z:
        for i in range(count):
            z.writestr(f"entry-{i}.xml", "x")
    return buf.getvalue()


class FileBoundsTests(unittest.TestCase):
    def test_xlsx_rejects_invalid_zip_and_too_many_entries(self):
        with self.assertRaises(HTTPException) as invalid:
            server._validate_xlsx_bounds(b"not a zip")
        self.assertEqual(invalid.exception.status_code, 400)

        with self.assertRaises(HTTPException) as too_many:
            server._validate_xlsx_bounds(zip_with_entries(server.MAX_XLSX_ENTRIES + 1))
        self.assertEqual(too_many.exception.status_code, 413)

    def test_pdf_pixel_budget_rejects_oversized_pages(self):
        page = SimpleNamespace(rect=SimpleNamespace(width=1_000_000, height=1_000_000))
        with self.assertRaises(HTTPException) as oversized:
            server._check_pdf_render_budget([page], 240)
        self.assertEqual(oversized.exception.status_code, 413)

    def test_image_dimensions_are_bounded(self):
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (12000, 1), "white").save(buf, format="PNG")
        with self.assertRaises(HTTPException) as too_wide:
            server._validate_image_dimensions(buf.getvalue())
        self.assertEqual(too_wide.exception.status_code, 413)


if __name__ == "__main__":
    unittest.main()
