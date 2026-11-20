import base64
import io
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree
from zipfile import ZipFile

from backend import Bridge


class FirstRunExampleTests(unittest.TestCase):
    def test_example_and_document_share_table_without_opening_model_or_data(self):
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder) / "data"
            bridge = Bridge(Path(folder) / "room", data_dir=data)
            result = bridge.call("api_example_task")
            self.assertTrue(result["ok"], result)
            sample = result["data"]
            result = bridge.call("api_example_document")
            self.assertTrue(result["ok"], result)
            document = result["data"]
            self.assertEqual(sample["file_name"], document["name"])
            self.assertEqual(len(sample["jobs"]), 2)
            blob = base64.b64decode(document["content_base64"], validate=True)
            with ZipFile(io.BytesIO(blob)) as archive:
                xml = ElementTree.fromstring(archive.read("word/document.xml"))
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            rows = xml.findall(".//w:tbl/w:tr", ns)
            self.assertEqual(len(rows), 4)
            self.assertIsNotNone(rows[0].find("w:trPr/w:tblHeader", ns))
            cells = [[cell.find(".//w:t", ns).text for cell in row.findall("w:tc", ns)] for row in rows]
            self.assertEqual(cells, [sample["table"]["columns"], *sample["table"]["rows"]])
            self.assertIsNone(bridge._auto)
            self.assertIsNone(bridge._workstation)
            self.assertFalse(data.exists())

    def test_fixed_example_calls_reject_supplied_input(self):
        with tempfile.TemporaryDirectory() as folder:
            bridge = Bridge(Path(folder) / "room", data_dir=Path(folder) / "data")
            for action in ("api_example_task", "api_example_document"):
                with self.subTest(action=action):
                    self.assertFalse(bridge.call(action, {"content": "other"})["ok"])
                    self.assertFalse(bridge.call(action, [])["ok"])


if __name__ == "__main__":
    unittest.main()
