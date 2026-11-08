import contextlib
from dataclasses import replace
import datetime
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests
import pull_whop as app
from whop_config import ConfigError, load_config, select_channels, validate_credentials

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / 'config.example.txt').read_text(encoding='utf-8')
# Dummy credentials solely for mocked tests, not a real session.
VALID = TEMPLATE.replace('value =\n', 'value = dummy_session=test-only; x=100%25\n').replace('chat_feed_REPLACE_1', 'chat_feed_TEST1').replace('chat_feed_REPLACE_2', 'chat_feed_TEST2')


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'config.txt'

    def read(self, text=VALID, bom=False):
        self.path.write_text(text, encoding='utf-8-sig' if bom else 'utf-8')
        return load_config(self.path)

    def test_example_contains_no_prompt_or_cookie(self):
        s = self.read(TEMPLATE)
        self.assertEqual(s.prompt, '')
        self.assertEqual(s.cookie, '')
        with self.assertRaises(ConfigError): validate_credentials(s, s.channels)

    def test_cookie_literal_and_prefix(self):
        s = self.read(VALID.replace('value = dummy', 'value = Cookie: dummy'))
        self.assertEqual(s.cookie, 'dummy_session=test-only; x=100%25')

    def test_bom_unicode_and_multiline_prompt(self):
        text = VALID.replace('Channel One', '频道甲').replace('text =\n', 'text =\n    # 我的标题\n    比例 100% ; a=b # 保留\n\n    [这是prompt文本]\n    最后一行\n')
        s = self.read(text, bom=True)
        self.assertEqual(s.channels[0].name, '频道甲')
        self.assertEqual(s.prompt, '# 我的标题\n比例 100% ; a=b # 保留\n\n[这是prompt文本]\n最后一行')

    def test_relative_output_uses_config_directory(self):
        self.assertEqual(self.read().output_file, self.path.parent / 'output/whop_chat.md')

    def test_missing_config(self):
        with self.assertRaises(ConfigError): load_config(self.path)

    def test_bad_ini_does_not_echo_cookie(self):
        secret = 'SHOULD_NOT_APPEAR_IN_ERROR'
        with self.assertRaises(ConfigError) as cm:
            self.read('[cookie]\nvalue = ' + secret + '\nvalue = second\n')
        self.assertNotIn(secret, str(cm.exception))

    def test_duplicate_feed(self):
        with self.assertRaises(ConfigError): self.read(VALID.replace('chat_feed_TEST2', 'chat_feed_TEST1'))

    def test_bad_feed(self):
        with self.assertRaises(ConfigError): self.read(VALID.replace('chat_feed_TEST1', 'not-a-feed'))

    def test_empty_channel_list(self):
        with self.assertRaises(ConfigError): self.read(VALID.replace('Channel One = chat_feed_TEST1\nChannel Two = chat_feed_TEST2\n', ''))

    def test_invalid_ranges_and_booleans(self):
        for old, new in [('hours_back = 48', 'hours_back = 0'), ('hours_back = 48', 'hours_back = nan'), ('max_pages = 1000', 'max_pages = 0'), ('request_delay = 1', 'request_delay = -1'), ('include_prompt = true', 'include_prompt = banana')]:
            with self.subTest(new=new), self.assertRaises(ConfigError): self.read(VALID.replace(old, new))

    def test_no_header_injection(self):
        with self.assertRaises(ConfigError): self.read(VALID.replace('value = dummy_session=test-only; x=100%25', 'value = dummy\n    injected'))

    def test_no_unknown_sections_or_keys(self):
        for text in [VALID + '\n[extra]\na=b\n', VALID.replace('hours_back', 'hours_bak'), VALID + '\n[DEFAULT]\nvalue=secret\n']:
            with self.assertRaises(ConfigError): self.read(text)

    def test_output_must_be_markdown(self):
        with self.assertRaises(ConfigError): self.read(VALID.replace('output/whop_chat.md', 'config.txt'))

    def test_select_single_by_name_index_or_id(self):
        s = self.read()
        for selector in ['1', 'Channel One', 'chat_feed_TEST1']:
            self.assertEqual(select_channels(s.channels, [selector]), [s.channels[0]])

    def test_multi_selection_deduplicates_preserves_order(self):
        s = self.read()
        self.assertEqual(select_channels(s.channels, ['2', '1', '2']), [s.channels[1], s.channels[0]])
        self.assertEqual(select_channels(s.channels, ['all']), s.channels)
        for selectors in [['missing'], ['3'], ['all', '1']]:
            with self.assertRaises(ConfigError): select_channels(s.channels, selectors)

    def test_only_selected_placeholders_validated(self):
        s = self.read(VALID.replace('chat_feed_TEST2', 'chat_feed_REPLACE_2'))
        validate_credentials(s, select_channels(s.channels, ['1']))
        with self.assertRaises(ConfigError): validate_credentials(s, s.channels)

    def test_no_network_list_or_check(self):
        self.read()
        with patch.object(app.requests, 'post') as post, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(app.main(['--config', str(self.path), '--list-channels']), 0)
            self.assertEqual(app.main(['--config', str(self.path), '--check-config', '--channels', '1', '2']), 0)
            post.assert_not_called()
            self.assertNotIn('dummy_session', output.getvalue())


class ExportTests(unittest.TestCase):
    @staticmethod
    def response(posts=None, users=None, status=200, body=None):
        return Mock(status_code=status, json=Mock(return_value=body if body is not None else {'data': {'messages': {'posts': posts or [], 'users': users or []}}}))

    @staticmethod
    def post(pid='p1', stamp=1500, cursor='1500000000000000000', **kwargs):
        return dict(id=pid, createdAt=stamp, sortKey=cursor, userId='u1', content='hello', **kwargs)

    def fetch(self, **kwargs):
        return app.fetch_channel('chat_feed_TEST1', {'Cookie': 'dummy'}, 'query', 1000, 2000, delay=0, **kwargs)

    def test_timestamp_units_precision(self):
        for value in [1700000000, 1700000000000, 1700000000000000, '1700000000000000000']:
            self.assertEqual(app.ts_to_seconds(value), 1700000000)
        for value in [None, 'nan', 'invalid', -1]: self.assertEqual(app.ts_to_seconds(value), 0)

    @patch.object(app.requests, 'post')
    def test_pagination_filters_window_duplicates_deleted(self, post):
        post.side_effect = [self.response([self.post('p1'), self.post('future', 2500, '1600000000000000000'), self.post('del', 1400, '1400000000000000000', isDeleted=True)], [{'id': 'u1', 'username': 'Example'}]), self.response([self.post('p1'), self.post('p2', 1200, '1200000000000000000'), self.post('old', 900, '900000000000000000')])]
        posts, users = self.fetch()
        self.assertEqual([p['id'] for p in posts], ['p1', 'p2'])
        self.assertEqual(users['u1'], 'Example')
        self.assertEqual(post.call_args_list[1].kwargs['json']['variables']['before'], '1400000000000000000')
        self.assertFalse(post.call_args.kwargs['allow_redirects'])
        self.assertEqual(post.call_args.args[0], app.URL)

    @patch.object(app.requests, 'post')
    def test_empty_channel(self, post):
        post.return_value = self.response()
        self.assertEqual(self.fetch(), ([], {}))

    @patch.object(app.requests, 'post')
    def test_repeated_cursor_stops(self, post):
        post.return_value = self.response([self.post()])
        with self.assertRaisesRegex(app.ExportError, '游标'): self.fetch()
        self.assertEqual(post.call_count, 2)

    @patch.object(app.requests, 'post')
    def test_max_pages_is_not_success(self, post):
        post.return_value = self.response([self.post()])
        with self.assertRaisesRegex(app.ExportError, 'max_pages'): self.fetch(max_pages=1)

    @patch.object(app.requests, 'post')
    def test_http_status_no_raw_response(self, post):
        for status in [401, 403, 429, 500, 302]:
            post.return_value = self.response(status=status)
            with self.assertRaises(app.ExportError): self.fetch()

    @patch.object(app.requests, 'post')
    def test_graphql_partial_errors_rejected(self, post):
        post.return_value = self.response(body={'data': {'messages': {'posts': []}}, 'errors': [{'message': 'SECRET_DO_NOT_ECHO'}]})
        with self.assertRaises(app.ExportError) as cm: self.fetch()
        self.assertNotIn('SECRET_DO_NOT_ECHO', str(cm.exception))

    @patch.object(app.requests, 'post')
    def test_invalid_json_and_response_shape(self, post):
        post.return_value = Mock(status_code=200, json=Mock(side_effect=ValueError('secret')))
        with self.assertRaises(app.ExportError): self.fetch()
        for body in [[], {'data': None}, {'data': {'messages': {}}}]:
            post.return_value = self.response(body=body)
            with self.assertRaises(app.ExportError): self.fetch()

    @patch.object(app.requests, 'post')
    def test_network_exception_is_redacted(self, post):
        post.side_effect = requests.exceptions.ConnectionError('COOKIE_SECRET')
        with self.assertRaises(app.ExportError) as cm: self.fetch()
        self.assertNotIn('COOKIE_SECRET', str(cm.exception))

    @patch.object(app.requests, 'post')
    def test_bad_timestamp_rejected(self, post):
        post.return_value = self.response([self.post(stamp='invalid')])
        with self.assertRaises(app.ExportError): self.fetch()

    def test_format_admin_reply_and_attachment_placeholder(self):
        p = self.post(isPosterAdmin=True, replyingToPost={'content': 'earlier', 'user': {'username': 'Original'}})
        rendered = app.format_channel('Channel', [p], {'u1': 'Example'})
        self.assertIn('【管理员】Example', rendered)
        self.assertIn('回复 Original', rendered)
        p['content'] = ''; p['attachments'] = [{'id': 'a'}]
        self.assertIn('1个附件', app.format_channel('Channel', [p], {}))

    def test_prompt_optional_and_cookie_not_in_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config.txt'
            path.write_text(VALID.replace('text =\n', 'text =\n    CUSTOM_PROMPT_MARKER\n'), encoding='utf-8')
            s = load_config(path)
            data = [(s.channels[0], [self.post()], {'u1': 'Example'})]
            now = datetime.datetime.now(datetime.timezone.utc)
            md = app.build_markdown(s, data, now)
            self.assertTrue(md.startswith('CUSTOM_PROMPT_MARKER'))
            self.assertNotIn(s.cookie, md)
            self.assertNotIn('CUSTOM_PROMPT_MARKER', app.build_markdown(s, data, now, False))
            self.assertNotIn('CUSTOM_PROMPT_MARKER', app.build_markdown(replace(s, include_prompt=False), data, now))

    @patch.object(app.requests, 'post')
    def test_main_multiple_channels_end_to_end_mocked(self, post):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config.txt'; path.write_text(VALID, encoding='utf-8')
            now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
            post.side_effect = [self.response([self.post(stamp=now), self.post('old', now-200000, '1')]), self.response()]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(app.main(['--config', str(path), '--channels', '1', '2', '--no-clipboard']), 0)
            md = (Path(tmp) / 'output/whop_chat.md').read_text(encoding='utf-8')
            self.assertIn('频道：Channel One', md); self.assertIn('频道：Channel Two', md)
            self.assertNotIn('dummy_session', md)
            self.assertEqual(post.call_count, 2)

    @patch.object(app.requests, 'post')
    def test_failure_does_not_overwrite_previous_export(self, post):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config.txt'; path.write_text(VALID, encoding='utf-8')
            target = Path(tmp) / 'output/whop_chat.md'; target.parent.mkdir(); target.write_text('previous export')
            post.side_effect = [self.response(), self.response(status=429)]
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(app.main(['--config', str(path), '--all', '--no-clipboard']), 1)
            self.assertEqual(target.read_text(), 'previous export')

    def test_atomic_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'output' / 'chat.md'
            app.write_atomic(path, 'hello 中文')
            self.assertEqual(path.read_text(encoding='utf-8'), 'hello 中文')
            self.assertEqual(list(path.parent.glob('*.tmp')), [])


if __name__ == '__main__':
    unittest.main()
