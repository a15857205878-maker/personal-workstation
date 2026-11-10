import json
import unittest
from session_reader import CodexSessionReader


def public(text, role='user'):
    return CodexSessionReader._public_message({'type': 'response_item', 'payload': {
        'type': 'message', 'role': role, 'phase': 'final_answer',
        'content': [{'type': 'input_text', 'text': text}]}}, 123)


class HistoryPresentationTest(unittest.TestCase):
    def test_pure_app_envelopes_are_not_chat_messages(self):
        self.assertIsNone(public('<external_codex_apps_open_page>{"page_id":null}</external_codex_apps_open_page>'))
        self.assertIsNone(public('<environment_context>PRIVATE_PATH</environment_context>'))

    def test_ambient_browser_context_is_removed_but_request_remains(self):
        result = public('<in-app-browser-context source="ambient-ui-state">PRIVATE_URL</in-app-browser-context>\n\n## My request:\n帮我处理这张图片')
        self.assertEqual(result['text'], '帮我处理这张图片')
        self.assertEqual(result['id'], '123')

    def test_question_reply_displays_question_and_answer(self):
        payload = json.dumps([{'questionItemId': 'INTERNAL_ID', 'question': '页面打开了吗？', 'answer': '可以'}], ensure_ascii=False)
        result = public('<send_user_message_question_reply>\n' + payload + '\n</send_user_message_question_reply>')
        self.assertEqual(result['text'], '页面打开了吗？\n可以')

    def test_code_and_real_instructions_are_unchanged(self):
        examples = ['请运行 python app.py --port 8765', '```xml\n<environment_context>example</environment_context>\n```',
                    '解释这个标记：<external_codex_apps_open_page>{}</external_codex_apps_open_page>',
                    '<environment_context>example</environment_context>\n请解释上面的XML',
                    '<environment_context>one</environment_context>\n请比较这两段XML\n<environment_context>two</environment_context>',
                    '<send_user_message_question_reply>invalid</send_user_message_question_reply>']
        for text in examples:
            self.assertEqual(public(text)['text'], text)
        text = '<external_codex_apps_open_page>{}</external_codex_apps_open_page>'
        self.assertEqual(public(text, 'assistant')['text'], text)
