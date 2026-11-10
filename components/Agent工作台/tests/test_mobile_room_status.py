import json
import sqlite3
import tempfile
from pathlib import Path
import unittest
from contextlib import closing
from mobile_room_status import public_room_status
from remote_gateway import RemoteGateway
from tests.test_remote_gateway import FakeBridge

class MobileRoomTests(unittest.TestCase):
    def sample(self):
        return dict(overview_state='ready', observed_at=100, counts=dict(tasks=2, collaborations=1, active=1, attention=0),
                    notices=[dict(kind='done',at=99,title='PRIVATE',path='secret')],token='SECRET',tasks=['PRIVATE'])
    def test_public_contract_drops_private_fields(self):
        result=public_room_status(self.sample(),100)
        self.assertEqual(result['recent_completed_at'],99)
        self.assertNotIn('PRIVATE',json.dumps(result));self.assertNotIn('SECRET',json.dumps(result))
        self.assertEqual(set(result),{'version','observed_at','overview_state','counts','recent_completed_at','scope','preview_kind'})
    def test_failed_partial_stale_future_or_invalid_counts_never_become_idle(self):
        for change in [dict(overview_state='unavailable'),dict(observed_at=80),dict(observed_at=110),dict(counts={'active':0}),dict(counts=dict(tasks=True,collaborations=0,active=0,attention=0))]:
            result=public_room_status({**self.sample(),**change},100)
            self.assertEqual(result['overview_state'],'unavailable');self.assertTrue(all(x is None for x in result['counts'].values()))
    def test_gateway_is_read_only_and_rejects_payload(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);bridge=FakeBridge(root);base=bridge.call;calls=[]
            def call(action,payload):
                calls.append((action,payload))
                if action=='workstation_butler_status':
                    import time
                    return {'ok':True,'data':{**self.sample(),'observed_at':time.time()}}
                return base(action,payload)
            bridge.call=call;gateway=RemoteGateway(bridge,root,port=0)
            result=gateway.rpc({'action':'room_status','payload':{}})
            self.assertTrue(result['ok'],result);self.assertEqual(calls,[('workstation_butler_status',{})])
            with closing(sqlite3.connect(gateway.db_path)) as db:self.assertEqual(db.execute('select count(*) from receipts').fetchone()[0],0)
            self.assertFalse(gateway.rpc({'action':'room_status','payload':{'path':'private'}})['ok'])

if __name__=='__main__':unittest.main()
