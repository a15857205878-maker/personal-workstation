import unittest,tempfile,sys,json,threading,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from credential_store import ProfileStore

class AntigravityTests(unittest.TestCase):
    def test_profile_has_no_key(self):
        with tempfile.TemporaryDirectory() as d:
            s=ProfileStore(d);p=s.save(dict(name='Gemini',kind='antigravity_local',model='gemini-test'))
            self.assertEqual(p['base_url'],'antigravity://local');self.assertFalse(p['requires_key'])
            self.assertEqual(s.credentials(p['id'])[1],'')
            self.assertEqual(len(s.list()),1)
    def channel(self,mode):
        from antigravity_channel import AntigravityChannel
        d=tempfile.TemporaryDirectory();self.addCleanup(d.cleanup)
        script=Path(d.name)/'fake.py'
        script.write_text("""import sys,json,time
mode=sys.argv[1]
if mode=='models':print('gemini-test\\tGemini Test');sys.exit()
request=json.loads(sys.stdin.readline())
assert request['event']=='user' and 'hello' in request['message']['content']
if mode=='stall':time.sleep(15)
if mode=='tool':print(json.dumps({'event':'step_update','step_update':{'step_type':'tool'}}))
print(json.dumps({'event':'result','result':{'status':'ERROR' if mode=='fail' else 'SUCCESS','response':'public reply','usage':{'input_tokens':10,'output_tokens':3}}}))
""",encoding='utf-8')
        return AntigravityChannel(finder=lambda:sys.executable,command_factory=lambda exe,args:[exe,str(script),mode])
    def test_complete_only_final_public_response(self):
        chunks=[];r=self.channel('ok').complete({'model':'gemini-test'},'',[{'role':'user','content':'hello'}],128,threading.Event(),chunks.append,time.time()+5)
        self.assertEqual(r['content'],'public reply');self.assertEqual(chunks,['public reply']);self.assertEqual(r['usage']['prompt_tokens'],10)
    def test_fail_and_tool_not_delivered(self):
        from provider_client import ProviderError
        for mode in ('fail','tool'):
            chunks=[]
            with self.assertRaises(ProviderError):self.channel(mode).complete({'model':'gemini-test'},'',[{'role':'user','content':'hello'}],128,threading.Event(),chunks.append,time.time()+5)
            self.assertEqual(chunks,[])
    def test_cancellation(self):
        from provider_client import Cancelled
        c=threading.Event();timer=threading.Timer(.2,c.set);timer.start()
        try:
            with self.assertRaises(Cancelled):self.channel('stall').complete({'model':'gemini-test'},'',[{'role':'user','content':'hello'}],128,c,lambda _:None,time.time()+4)
        finally:timer.cancel()
    def test_settings_and_stdin_command(self):
        from antigravity_channel import command,SETTINGS
        args=command('agy.exe',['--model','gemini-test'])
        self.assertNotIn('--dangerously-skip-permissions',args);self.assertIn('--disable-slash-commands',args)
        self.assertIn('mcp(*)',SETTINGS['permissions']['deny']);self.assertIn('read_file(*)',SETTINGS['permissions']['deny'])
    def test_cancelled_or_expired_does_not_spawn(self):
        from unittest.mock import patch
        from provider_client import ProviderError
        channel=self.channel('ok')
        for cancelled,deadline in ((True,time.time()+5),(False,time.time()-1)):
            c=threading.Event()
            if cancelled:c.set()
            with patch('antigravity_channel.subprocess.Popen') as spawn:
                with self.assertRaises(ProviderError):channel.complete({'model':'gemini-test'},'',[{'role':'user','content':'hello'}],128,c,lambda _:None,deadline)
                spawn.assert_not_called()
    def test_global_customizations_fail_closed_and_empty_install_allowed(self):
        from antigravity_channel import check_customizations
        from provider_client import ProviderError
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);base=root/'.gemini/config';base.mkdir(parents=True)
            (base/'plugins').mkdir();(base/'mcp_config.json').touch()
            check_customizations(root)
            (base/'hooks.json').write_text('{}')
            with self.assertRaises(ProviderError):check_customizations(root)

if __name__=='__main__':unittest.main()
