import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock

from network_access import read_tailscale, NetworkAccess


class NetworkAccessTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.exe=Path(self.tmp.name)/'tailscale.exe';self.exe.write_bytes(b'fake executable')

    def tearDown(self):self.tmp.cleanup()

    def probe(self,payload):
        return read_tailscale(self.exe,runner=Mock(return_value=subprocess.CompletedProcess([],0,json.dumps(payload),'')))

    def test_connected_returns_only_private_device_address_without_account_data(self):
        state=self.probe({'BackendState':'Running','TailscaleIPs':['100.90.1.2','fd7a::1','8.8.8.8'],'Self':{'Online':True},'AuthURL':'private-login','Peer':{'private':'data'}})
        self.assertEqual(state['state'],'connected')
        self.assertEqual(state['ipv4'],['100.90.1.2'])
        self.assertNotIn('private',json.dumps(state))

    def test_login_approval_and_stopped_do_not_advertise_remote_addresses(self):
        for backend,expected in [('NeedsLogin','needs_login'),('NeedsMachineAuth','needs_approval'),('Stopped','offline')]:
            state=self.probe({'BackendState':backend,'TailscaleIPs':['100.90.1.2']})
            self.assertEqual(state['state'],expected)
            self.assertEqual(state['ipv4'],[])

    def test_uninstalled_and_timeout_keep_app_usable(self):
        self.assertEqual(read_tailscale(self.exe.with_name('missing.exe'))['state'],'not_installed')
        runner=Mock(side_effect=subprocess.TimeoutExpired('tailscale',2))
        self.assertEqual(read_tailscale(self.exe,runner=runner)['state'],'unavailable')

    def test_invalid_status_is_not_treated_as_connected(self):
        runner=Mock(return_value=subprocess.CompletedProcess([],0,'invalid JSON',''))
        self.assertEqual(read_tailscale(self.exe,runner=runner)['state'],'unavailable')
        self.assertEqual(self.probe({'BackendState':'Running','TailscaleIPs':['not an address']})['ipv4'],[])
        self.assertEqual(self.probe({'BackendState':'Running','TailscaleIPs':['100.90.1.2'],'Self':{'Online':False}})['state'],'offline')

    def test_connected_after_startup_adds_remote_url_and_offline_removes_it(self):
        states=[{'state':'needs_login','ipv4':[],'message':'待登录'}, {'state':'connected','ipv4':['100.90.1.2'],'message':'已连接'}, {'state':'offline','ipv4':[],'message':'离线'}]
        now=[0]
        probe=Mock(side_effect=states)
        lan=['http://192.168.3.4:8765/?token=paired']
        access=NetworkAccess(lan,8765,'paired',probe=probe,clock=lambda:now[0])
        self.assertEqual(access.snapshot()['urls'],lan)
        access.snapshot();self.assertEqual(probe.call_count,1)
        now[0]=6
        self.assertEqual(access.snapshot()['urls'],lan+['http://100.90.1.2:8765/?token=paired'])
        now[0]=12
        self.assertEqual(access.snapshot()['urls'],lan)

    def test_virtual_adapter_address_is_not_kept_as_lan_when_disconnected(self):
        lan='http://192.168.3.4:8765/?token=paired'
        stale='http://100.90.1.2:8765/?token=paired'
        access=NetworkAccess([lan,stale],8765,'paired',probe=lambda:{'state':'offline','ipv4':[],'message':'离线'})
        self.assertEqual(access.snapshot()['urls'],[lan])
