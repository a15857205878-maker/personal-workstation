import json
import unittest
from diagnostics import diagnostic_report


class DiagnosticsTests(unittest.TestCase):
    def report(self, **changes):
        values = dict(network={'remote_access':{'state':'connected'}},
                      agent_list=[{'id':'codex','available':True}], task_list=[], jobs=[], uptime=12)
        values.update(changes)
        return diagnostic_report(**values)

    def test_safe_summary_uses_only_whitelisted_fields(self):
        secret = 'PRIVATE_TOKEN_URL_PATH_EMAIL_PROMPT'
        report = self.report(network={'urls':[secret],'remote_access':{'state':'connected','message':secret,'ipv4':[secret]}},
                             agent_list=[{'id':'codex','available':True,'path':secret}],
                             task_list=[{'status':'running','goal':secret,'id':secret}],
                             jobs=[{'status':'waiting','text':secret,'output':secret,'error':secret,'source':secret,'observed_status':'native_writer_busy'}])
        self.assertNotIn(secret,json.dumps(report,ensure_ascii=False))
        checks={item['id']:item for item in report['checks']}
        self.assertEqual(checks['receiver']['status'],'ok')
        self.assertEqual(checks['remote']['status'],'ok')
        self.assertEqual(checks['replies']['status'],'warn')
        self.assertIn('最近',checks['replies']['detail'])
        self.assertIn('登录',checks['agent']['detail'])
        self.assertIn('额度',checks['agent']['detail'])

    def test_pc_remote_state_does_not_claim_phone_is_connected(self):
        check=next(item for item in self.report()['checks'] if item['id']=='remote')
        self.assertIn('电脑',check['label'])
        self.assertIn('手机',check['action'])

    def test_partial_failures_are_unknown_not_success(self):
        report=self.report(network=None,agent_list=None,task_list=None,jobs=None)
        self.assertEqual([x['status'] for x in report['checks']],['ok','unknown','unknown','unknown','unknown'])
        self.assertNotIn('None',report['summary'])

    def test_not_installed_or_signed_out_are_actionable(self):
        for state in ('not_installed','needs_login','needs_approval','offline','starting','unavailable'):
            report=self.report(network={'remote_access':{'state':state}},agent_list=[])
            checks={item['id']:item for item in report['checks']}
            self.assertNotEqual(checks['remote']['status'],'ok')
            self.assertEqual(checks['agent']['status'],'warn')

    def test_reply_scope_is_explicit_and_limited(self):
        report=self.report(jobs=[{'status':'queued'}]*20)
        check=next(item for item in report['checks'] if item['id']=='replies')
        self.assertIn('20',check['label'])
        self.assertIn('本网页',check['label'])
        self.assertIn('20',check['detail'])
