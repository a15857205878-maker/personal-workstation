import json,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from seat_styles import styles_for
from chat_service import chat_tone
from auto_service import AutoService

class PersonaTests(unittest.TestCase):
    def test_legacy_style_uses_embedded_prompt_without_reading_local_plugin(self):
        service=AutoService.__new__(AutoService)
        with patch.object(Path,'read_text',side_effect=AssertionError('Local plugin must not be read')):
            text=service._persona('qinghe')
        self.assertIn('温和',text);self.assertIn('真实',text)
    def test_new_presets_snapshot_full_persona_and_lexicon(self):
        styles=styles_for({'seat_styles':{'A':{'preset':'lele'},'B':{'preset':'jingshui'}}})
        self.assertIn('协作助手',chat_tone(styles['A']));self.assertIn('审阅助手',chat_tone(styles['B']))
        self.assertIn('表达示例',chat_tone(styles['A']))
        self.assertIn('词库只是',chat_tone(styles['B']))
        self.assertIn('resolved_text',styles['A'])
        self.assertNotIn('阿满',chat_tone(styles['A']))
        self.assertIn('不编造经历',chat_tone(styles['A']))
    def test_saved_snapshot_is_used_and_old_styles_remain_compatible(self):
        self.assertEqual(chat_tone(dict(preset='lele',text='',resolved_text='SAVED_PERSONA')),'SAVED_PERSONA')
        self.assertIn('友善',chat_tone(styles_for({})['A']))
        self.assertIn('温和',chat_tone(styles_for({'persona':'qinghe'})['B']))
        with self.assertRaises(ValueError):styles_for({'seat_styles':{'A':{'preset':'lele','resolved_text':'x'*12001}}})
    def test_imported_catalog_contains_all_dimensions_and_recipes(self):
        catalog=json.loads((Path(__file__).resolve().parents[1]/'persona_catalog.json').read_text(encoding='utf-8'))
        self.assertEqual([p['id'] for p in catalog['presets']],['lele','jingshui'])
        self.assertEqual(len(catalog['dimensions']),9);self.assertEqual(len(catalog['recipes']),8)
        self.assertTrue(all(len(p['text'])>200 for p in catalog['presets']))
        self.assertEqual(catalog['version'],3)
        self.assertIn('通用表达模板',catalog['human_template'])
        self.assertIn('不替用户决定',catalog['human_guidance'])
        for p in catalog['presets']:
            for field in ('关系','想要','怕','规则','语言指纹','状态档','记忆','边界','禁用句'):
                self.assertIn('**'+field+'**',p['text'])
        self.assertIn('不虚构记忆或执行结果',catalog['presets'][0]['text'])

if __name__=='__main__':unittest.main()
