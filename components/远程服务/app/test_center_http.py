import unittest,json
import test_workbench_http as fixtures
from workbench_proxy import WorkbenchProxy

class CenterHTTPTests(unittest.TestCase):
    setUp=fixtures.WorkbenchHTTPTests.setUp
    tearDown=fixtures.WorkbenchHTTPTests.tearDown
    request=fixtures.WorkbenchHTTPTests.request
    def test_page_requires_pairing_and_rpc_rejects_cross_origin(self):
        self.assertEqual(self.request('/agent-center')[0],403)
        code,body=self.request('/agent-center?token=paired-test')
        self.assertEqual(code,200);self.assertIn(b'center_bootstrap',body);self.assertIn(b'id="composer"',body)
        self.assertEqual(self.request('/api/workbench?token=paired-test',{'action':'center_bootstrap','payload':{}},headers={'Origin':'https://evil.invalid'})[0],403)
    def test_proxy_only_forwards_fixed_center_fields(self):
        calls=[];self.server.workbench=WorkbenchProxy(self.temp.name,self.temp.name,transport=lambda a,p,r:(calls.append((a,p,r)) or {'ok':True,'data':{'sessions':[]}}))
        self.assertEqual(self.request('/api/workbench?token=paired-test',{'action':'center_bootstrap','payload':{}})[0],200)
        code,body=self.request('/api/workbench?token=paired-test',{'action':'center_get','payload':{'id':'a'*32,'path':'secret'}})
        self.assertEqual(code,400);self.assertEqual(len(calls),1)

if __name__=='__main__':unittest.main()
