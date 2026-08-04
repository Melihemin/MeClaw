import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.finder.explorer_class import Explorer


class ExplorerClassTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.explorer = Explorer(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_create_read_write_and_delete_file(self) -> None:
        result = self.explorer.create_file("notes.txt")
        self.assertIn("created successfully", result)

        read_result = self.explorer.read_file("notes.txt")
        self.assertEqual(read_result, "")

        write_result = self.explorer.write_file("notes.txt", "hello world")
        self.assertIn("successfully", write_result)

        self.assertEqual(self.explorer.read_file("notes.txt"), "hello world")

        delete_result = self.explorer.delete_file("notes.txt")
        self.assertIn("deleted successfully", delete_result)
        self.assertFalse(Path(self.temp_dir.name, "notes.txt").exists())

    def test_copy_rename_and_folder_operations(self) -> None:
        self.explorer.create_file("source.txt")
        self.explorer.write_file("source.txt", "data")

        copy_result = self.explorer.copy_file("source.txt", "target.txt")
        self.assertIn("copied", copy_result)
        self.assertEqual(self.explorer.read_file("target.txt"), "data")

        rename_result = self.explorer.rename_file("target.txt", "renamed.txt")
        self.assertIn("renamed", rename_result)
        self.assertTrue(Path(self.temp_dir.name, "renamed.txt").exists())

        folder_result = self.explorer.create_folder("nested")
        self.assertIn("created successfully", folder_result)
        self.assertTrue(Path(self.temp_dir.name, "nested").is_dir())

        remove_result = self.explorer.remove_folder("nested")
        self.assertIn("removed successfully", remove_result)

    def test_indexing_move_rename_copy_folder_and_zip(self) -> None:
        self.explorer.create_file("alpha.txt")
        self.explorer.create_folder("docs")
        self.explorer.write_file("docs/child.txt", "hello")

        indexed = self.explorer.list_items()
        self.assertTrue(any(item["name"] == "alpha.txt" for item in indexed))
        self.assertTrue(any(item["name"] == "docs" for item in indexed))

        move_result = self.explorer.move_item("alpha.txt", "docs/alpha.txt")
        self.assertIn("moved", move_result)
        self.assertFalse(Path(self.temp_dir.name, "alpha.txt").exists())
        self.assertTrue(Path(self.temp_dir.name, "docs", "alpha.txt").exists())

        rename_folder_result = self.explorer.rename_folder("docs", "archive")
        self.assertIn("renamed", rename_folder_result)
        self.assertTrue(Path(self.temp_dir.name, "archive").is_dir())

        copy_folder_result = self.explorer.copy_folder("archive", "backup")
        self.assertIn("copied", copy_folder_result)
        self.assertTrue(Path(self.temp_dir.name, "backup").is_dir())

        zip_result = self.explorer.zip_folder("backup")
        self.assertIn("zipped", zip_result)
        archive_path = Path(self.temp_dir.name, "backup.zip")
        self.assertTrue(archive_path.exists())
        with zipfile.ZipFile(archive_path) as archive:
            self.assertIn("child.txt", archive.namelist())

    def test_extract_archive(self) -> None:
        archive_path = Path(self.temp_dir.name, "sample.zip")
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr("nested/data.txt", "hello archive")

        extract_result = self.explorer.extract_archive("sample.zip", "extracted")
        self.assertIn("extracted", extract_result)
        self.assertTrue(Path(self.temp_dir.name, "extracted", "nested", "data.txt").exists())


if __name__ == "__main__":
    unittest.main()
