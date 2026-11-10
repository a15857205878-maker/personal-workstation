import sys,unittest,ast
from pathlib import Path
from types import SimpleNamespace
P=Path(__file__).resolve().parents[2]/'agent-desktop-pet'
sys.path.insert(0,str(P))
import pet_butler
import pet_appearance_catalog

class ButlerTests(unittest.TestCase):
    def test_combines_workstation_and_selected_agent_without_other_agents(self):
        h=SimpleNamespace(settings={'agent':'codex'})
        items=[{'agent':'workbench'},{'agent':'codex'},{'agent':'deepseek'}]
        self.assertEqual(pet_butler.visible_items(h,items),items[:2])
    def test_mark_one_checks_owner_and_stale_agent(self):
        h=SimpleNamespace(settings={'agent':'codex'})
        items=[{'id':'a','agent':'workbench'},{'id':'b','agent':'deepseek'}]
        self.assertEqual(pet_butler.read_scope(h,{'id':'a','agent':'codex'},items),'workbench')
        for data in ({'id':'b','agent':'codex'},{'id':'a','agent':'deepseek'}):
            with self.assertRaises(ValueError):pet_butler.read_scope(h,data,items)
    def test_tools_fixed_and_appearance_independent(self):
        for appearance in ('legacy','dragon'):
            calls=[];h=SimpleNamespace(settings={'petAppearance':appearance},toggle_metric_card=lambda:calls.append('quota'))
            pet_butler.open_tool(h,'quota');self.assertEqual(calls,['quota'])
            with self.assertRaises(ValueError):pet_butler.open_tool(h,'shell')
    def test_appearance_inventory_does_not_mix_assets(self):
        legacy=pet_appearance_catalog.catalog(P/'web','legacy')
        dragon=pet_appearance_catalog.catalog(P/'web','dragon')
        self.assertIn('ReactionNod:0',[m['id'] for m in dragon['motions']])
        self.assertNotIn('ReactionNod:0',[m['id'] for m in legacy['motions']])
        self.assertIn('呆呆眼',dragon['expressions'])
        self.assertNotEqual(legacy['expressions'],dragon['expressions'])
    def test_bulk_scopes_exclude_unselected_agents_and_reject_stale_ui(self):
        h=SimpleNamespace(settings={'agent':'codex'})
        self.assertEqual(pet_butler.scopes(h,{'agent':'codex'}),('codex','workbench'))
        with self.assertRaises(ValueError):pet_butler.scopes(h,{'agent':'deepseek'})
    def test_real_host_inventory_changes_on_character_switch(self):
        tree=ast.parse((P/'run.py').read_text(encoding='utf-8'))
        fn=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='_appearance_inventory')
        env={'WEB':str(P/'web')};exec(compile(ast.Module(body=[fn],type_ignores=[]),'run.py','exec'),env)
        host=SimpleNamespace(settings={'petAppearance':'legacy'})
        old=env['_appearance_inventory'](host)
        host.settings['petAppearance']='dragon';new=env['_appearance_inventory'](host)
        self.assertNotEqual(old['motions'],new['motions'])
        host.settings['petAppearance']='legacy';self.assertEqual(env['_appearance_inventory'](host),old)
    def test_unified_agent_tools_are_not_gated_by_character(self):
        from pet_panel_actions import apply_action
        for appearance in ('legacy','dragon'):
            calls=[];host=SimpleNamespace(settings={'petAppearance':appearance},toggle_metric_card=lambda:calls.append('quota'))
            apply_action(host,{'action':'tool','tool':'quota'})
            self.assertEqual(calls,['quota'])
            with self.assertRaises(ValueError):apply_action(host,{'action':'tool','tool':'quota','command':'anything'})
    def test_old_split_shim_no_longer_suppresses_agent_status(self):
        import pet_content_sections
        h=SimpleNamespace(settings={'agent':'codex'})
        message={'t':'state','data':{'state':'working'}}
        self.assertIs(pet_content_sections.filter_message(h,message),message)
        self.assertTrue(pet_content_sections.notification_visible(h,'workbench'))
        self.assertTrue(pet_content_sections.notification_visible(h,'codex'))

if __name__=='__main__':unittest.main()
