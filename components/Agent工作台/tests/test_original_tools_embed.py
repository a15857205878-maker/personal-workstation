import tempfile
from pathlib import Path
import unittest
from workstation_core import ToolProcess

class OriginalToolTests(unittest.TestCase):
    def test_original_game_create_edit_and_picker_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for path in ('个人工具中心/data','个人工具中心新版/data','游戏管家/data'):(root/path).mkdir(parents=True)
            class Picker:
                def create_file_dialog(self,*args,**kwargs):return None
            tools=ToolProcess(lambda:Picker(),test_root=root)
            try:
                added=tools.call('game_add',{'name':'隔离游戏','english_name':'Fixture','steam_appid':'123'})
                game=next(g for g in added['games'] if g['name']=='隔离游戏')
                edited=tools.call('game_save',{'id':game['id'],'name':'已修改','english_name':'Fixture','aliases':['别名'],'notes':'本地备注'})
                saved=next(g for g in edited['games'] if g['id']==game['id'])
                self.assertEqual((saved['name'],saved['aliases'],saved['notes']),('已修改',['别名'],'本地备注'))
                self.assertTrue(tools.call('game_add_tool',{'id':game['id']})['cancelled'])
                with self.assertRaises(ValueError):tools.call('game_add',{'name':'拒绝','steam_appid':'cmd.exe'})
            finally:tools.close()

if __name__=='__main__':unittest.main()
