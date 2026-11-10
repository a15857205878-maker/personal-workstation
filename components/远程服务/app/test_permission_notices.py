import json
import unittest
from adapters import NeedsAttention,parse_codex_event,parse_codex_result


class PermissionNoticeTests(unittest.TestCase):
    def test_executor_denial_has_safe_manual_next_step(self):
        with self.assertRaises(NeedsAttention) as caught:
            parse_codex_event({'type':'turn.failed','error':{'message':'Permission denied: PRIVATE_PATH_AND_SECRET'}},lambda *_:None,lambda *_:None)
        text=str(caught.exception)
        self.assertIn('需要你处理：权限',text);self.assertIn('电脑端',text);self.assertNotIn('PRIVATE',text)

    def test_nonpermission_errors_are_not_relabelled(self):
        for value in ['usage limit reached','connection failed']:
            with self.assertRaisesRegex(NeedsAttention,value):
                parse_codex_event({'type':'error','message':value},lambda *_:None,lambda *_:None)

    def test_permission_marked_completion_requires_attention(self):
        result={'status':'completed','summary':'[需要你处理：权限] 需要写入授权目录外，请先在电脑核对。','completed_parts':[]}
        with self.assertRaisesRegex(NeedsAttention,'电脑端'):
            parse_codex_result(json.dumps(result),lambda *_:None)

    def test_regular_explanation_is_not_a_permission_block(self):
        text='权限不足表示当前操作未获授权，这里只是解释术语。'
        result={'status':'completed','summary':text,'completed_parts':[]}
        self.assertEqual(parse_codex_result(json.dumps(result),lambda *_:None),text)

    def test_nonpermission_blocker_with_negated_approval_stays_unchanged(self):
        text='缺少输入文件，当前不需要额外授权。'
        with self.assertRaises(NeedsAttention) as caught:
            parse_codex_result(json.dumps({'status':'needs_attention','summary':text,'completed_parts':[]}),lambda *_:None)
        self.assertEqual(str(caught.exception),text)
