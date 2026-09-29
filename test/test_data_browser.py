"""읽기 전용 데이터 화면 API가 저장된 행과 봉인 문서 필터를 지키는지 확인한다."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import main
from app.db import connect, init_db


class DataBrowserTest(unittest.TestCase):
    def test_tables_rows_pagination_and_sealed_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "msds.sqlite"
            conn = connect(db_path)
            init_db(conn)
            with conn:
                conn.execute("INSERT INTO msds_documents (id,file_name,file_hash,model_name,raw_json,extracted_at) VALUES (1,'allowed.pdf',?,'qlora','{}','2026-09-29')", ("a" * 64,))
                conn.execute("INSERT INTO msds_documents (id,file_name,file_hash,model_name,raw_json,extracted_at) VALUES (2,'sealed.pdf',?,'qlora','{}','2026-09-29')", ("b" * 64,))
                conn.execute("INSERT INTO msds_ingredients (document_id,seq,chemical_name) VALUES (1,1,'visible')")
                conn.execute("INSERT INTO msds_ingredients (document_id,seq,chemical_name) VALUES (2,1,'hidden')")
            conn.close()
            with mock.patch.object(main, "DB_PATH", db_path), mock.patch.object(main, "sealed_hashes", return_value={"b" * 64}):
                client = TestClient(main.app)
                response = client.get("/data")
                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertEqual(body["total"], 1)
                self.assertEqual([row["file_name"] for row in body["rows"]], ["allowed.pdf"])
                self.assertEqual(next(item["count"] for item in body["tables"] if item["name"] == "msds_ingredients"), 1)
                ingredients = client.get("/data", params={"table": "msds_ingredients", "limit": 1, "offset": 0}).json()
                self.assertEqual([row["chemical_name"] for row in ingredients["rows"]], ["visible"])
                self.assertEqual(client.get("/data", params={"table": "sqlite_master"}).status_code, 422)
                self.assertEqual(client.get("/data", params={"limit": 101}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
