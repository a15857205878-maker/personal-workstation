from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
from test_station import FakeModels
from task_station.core import Service
from task_station.adapters import Adapters
from task_station.host import launch_plan

class OptionsTests(unittest.TestCase):
    def test_saved_catalog_keeps_custom_suffix_default_and_history(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            packaged=Path(__file__).resolve().parents[1]/'task_station/templates.json'
            saved=json.loads(packaged.read_text(encoding='utf-8'))
            ppt=next(t for t in saved['tasks'] if t['id']=='pptx')
            ppt['agents']=[{'role_ref':'presentation','label':'Claude自定义名称'}]
            ppt['suffix']='我自己修改的后缀'
            saved['tasks']=[t for t in saved['tasks'] if t['id']!='image']
            (root/'templates.json').write_text(json.dumps(saved),encoding='utf-8')
            raw=(root/'templates.json').read_bytes()
            fake=FakeModels()
            original=fake.capabilities
            fake.capabilities=lambda:{**original(), 'presentation_gemini':dict(label='Gemini PPT',mode='manual',can_run=False,detail='客户端'), 'image_gemini':dict(label='Gemini图片',mode='manual',can_run=False,detail='客户端')}
            s=Service(root,fake)
            try:
                ppt=next(t for t in s.call('catalog')['tasks'] if t['id']=='pptx')
                self.assertIn('presentation_gemini',[a['role_ref'] for a in ppt['agents']])
                self.assertEqual(ppt['default_role_ref'],'presentation_gemini')
                self.assertEqual(ppt['suffix'],'我自己修改的后缀')
                self.assertEqual(ppt['agents'][0]['label'],'Gemini')
                self.assertEqual((root/'templates.json').read_bytes(),raw)
                task=s.call('create',dict(task_type='pptx',role='presentation_gemini',instruction='新Gemini任务'))
                self.assertEqual(task['role'],'presentation_gemini')
                legacy=s.call('create',dict(task_type='pptx',role='presentation',instruction='旧客户端兼容'))
                self.assertEqual(legacy['role'],'presentation')
                image=s.call('create',dict(task_type='image',role='image_gemini',instruction='青绿色封面'))
                self.assertEqual(image['mode'],'manual')
            finally:s.close()

    def test_presentation_uses_api_but_image_requires_separate_image_model(self):
        class Ready:
            def public(self):return {k:dict(has_key=True,model='ready',base_url='https://example.invalid') for k in ('qwen','gemini')}
        a=Adapters.__new__(Adapters);a.settings=Ready();a.codex='local';a.harness=Path('does-not-exist')
        self.assertTrue(a.capabilities()['presentation_gemini']['can_run'])
        cap=a.capabilities()['image_gemini']
        self.assertFalse(cap['can_run']);self.assertEqual(cap['mode'],'needs_config');self.assertFalse(cap['can_review'])
        with patch('task_station.host.Path.is_file',return_value=False):
            for role in ('presentation_gemini','image_gemini'):
                self.assertEqual(launch_plan(role),('url','https://gemini.google.com/app'))

if __name__=='__main__':unittest.main()
