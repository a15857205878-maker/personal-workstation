from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from task_station.core import Service
from task_station.migration import import_station
from test_station import FakeModels


class MigrationTests(unittest.TestCase):
    def test_archived_tasks_files_and_repeat_import(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder)
            original=Service(base/'source',FakeModels())
            task=original.call('create',dict(task_type='text',role='text_1',instruction='保存来源'))
            file=base/'draft.md'; file.write_text('原稿',encoding='utf-8')
            original.import_file(task['id'],file)
            original.call('archive',{'id':task['id']})
            original.close()
            result=import_station(base/'source',base/'target')
            self.assertEqual(result['imported'],1)
            self.assertEqual(import_station(base/'source',base/'target')['imported'],0)
            target=Service(base/'target',FakeModels())
            try:
                rows=target.call('list',{'archived':True})
                self.assertEqual([r['id'] for r in rows],[task['id']])
                self.assertEqual(target.file_path(task['id'],'draft.md').read_text(encoding='utf-8'),'原稿')
            finally:target.close()

    def test_running_source_is_not_copied(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder)
            original=Service(base/'source',FakeModels())
            task=original.call('create',dict(task_type='text',role='text_1',instruction='保存来源'))
            task['status']='执行中'; original._save(task)
            original.close()
            with self.assertRaises(ValueError):import_station(base/'source',base/'target')
            self.assertFalse((base/'target/tasks.sqlite3').exists())
