import datetime
import threading
import types
import unittest

from xmonitor.services.dm import recent_contacts as rc


class FakeTab:
    def __init__(self, snapshots=None, fail_get=False, url='https://x.com/i/chat', redirect_url=''):
        self.snapshots = list(snapshots or [])
        self.visited = []
        self.closed = False
        self.scrolled = 0
        self.fail_get = fail_get
        self.url = url
        self.redirect_url = redirect_url

    def get(self, url):
        if self.fail_get:
            raise RuntimeError('network failed')
        self.visited.append(url)
        self.url = self.redirect_url or url

    def run_js(self, script):
        if 'window.scrollBy' in str(script):
            self.scrolled += 1
            return None
        if 'enter passcode' in str(script).lower():
            return ''
        return list(self.snapshots)

    def close(self):
        self.closed = True


class FakeBrowser:
    def __init__(self, tab):
        self.tab = tab

    def new_tab(self):
        return self.tab


class DmRecentContactsTests(unittest.TestCase):
    def test_parse_relative_age_seconds(self):
        self.assertEqual(rc._parse_relative_age_seconds('3分钟'), 180)
        self.assertEqual(rc._parse_relative_age_seconds('2 hours'), 7200)
        self.assertEqual(rc._parse_relative_age_seconds('刚刚'), 0)
        self.assertIsNone(rc._parse_relative_age_seconds('无时间'))

    def test_extract_contact_from_snapshot_prefers_avatar_handle(self):
        row = {
            'raw_text': '张三\n您好\n上午 10:12',
            'avatar_handles': ['UserAvatar-Container-demo_user'],
            'time_texts': ['上午 10:12'],
        }
        parsed = rc._extract_contact_from_snapshot(row)
        self.assertEqual(parsed['name'], '张三')
        self.assertEqual(parsed['handle'], '@demo_user')

    def test_format_contacts_for_copy(self):
        text = rc.format_contacts_for_copy([
            {'name': '张三', 'handle': '@demo'},
            {'name': '@only', 'handle': '@only'},
            {'name': 'missing'},
        ])
        self.assertEqual(text, '@demo\n@only')

    def test_scan_recent_dm_contacts_filters_old_rows_and_dedupes(self):
        now = datetime.datetime(2026, 5, 12, 12, 0, 0)
        tab = FakeTab([
            {'raw_text': '张三\n3分钟\nhello', 'avatar_handles': ['demo'], 'time_texts': ['3分钟'], 'is_conversation': True},
            {'raw_text': '张三\n3分钟\nhello again', 'avatar_handles': ['demo'], 'time_texts': ['3分钟'], 'is_conversation': True},
            {'raw_text': '李四\n2天\nold', 'avatar_handles': ['old_user'], 'time_texts': ['2天'], 'is_conversation': True},
            {'raw_text': '', 'avatar_handles': ['manateelazycat'], 'time_texts': []},
        ])

        result = rc.scan_recent_dm_contacts(tab, sleep_fn=lambda _s: None, now_fn=lambda: now, max_scrolls=1)

        self.assertEqual(tab.visited, [rc.CHAT_URL])
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['contacts'][0]['handle'], '@demo')
        self.assertEqual(result['stale_rows'], 1)
        self.assertEqual(result['copy_text'], '@demo')

    def test_scan_recent_dm_contacts_ignores_side_nav_avatar_without_message_signal(self):
        tab = FakeTab([
            {'raw_text': '', 'avatar_handles': ['manateelazycat'], 'time_texts': []},
        ])

        result = rc.scan_recent_dm_contacts(tab, sleep_fn=lambda _s: None, max_scrolls=1)

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['contacts'], [])
        self.assertEqual(result['copy_text'], '')

    def test_scan_recent_dm_contacts_supports_new_x_i_chat_rows(self):
        now = datetime.datetime(2026, 5, 12, 12, 0, 0)
        tab = FakeTab([
            {
                'raw_text': 'xLight 2h You: 老板您好呀，最近在看咱们的产品',
                'hrefs': ['/i/chat/6784722-28530405', 'https://x.com/xlight'],
                'avatar_handles': [],
                'time_texts': [],
                'is_conversation': True,
            },
            {
                'raw_text': 'KakaOrca 15h You: 我们感兴趣',
                'hrefs': ['/i/chat/28530405-1897103735278723073', 'https://x.com/KakaOrca'],
                'avatar_handles': [],
                'time_texts': [],
                'is_conversation': True,
            },
            {
                'raw_text': '',
                'hrefs': ['https://x.com/manateelazycat'],
                'avatar_handles': ['manateelazycat'],
                'time_texts': [],
            },
        ])

        result = rc.scan_recent_dm_contacts(tab, sleep_fn=lambda _s: None, now_fn=lambda: now, max_scrolls=1)

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['count'], 2)
        self.assertEqual(result['contacts'][0]['name'], 'xLight')
        self.assertEqual(result['contacts'][0]['handle'], '@xlight')
        self.assertEqual(result['contacts'][0]['age_seconds'], 7200)
        self.assertEqual(result['contacts'][1]['name'], 'KakaOrca')
        self.assertEqual(result['contacts'][1]['handle'], '@KakaOrca')
        self.assertEqual(result['copy_text'], '@xlight\n@KakaOrca')

    def test_scan_recent_dm_contacts_returns_error_on_passcode_block(self):
        tab = FakeTab([], redirect_url='https://x.com/i/chat/pin/recovery?from=%2Fi%2Fchat')

        result = rc.scan_recent_dm_contacts(tab, sleep_fn=lambda _s: None, max_scrolls=1)

        self.assertEqual(result['status'], 'err')
        self.assertIn('Enter Passcode', result['msg'])

    def test_scan_recent_dm_contacts_with_browser_closes_tab_and_saves_result(self):
        tab = FakeTab([
            {'raw_text': '王五\n1小时\nhello', 'avatar_handles': ['wangwu'], 'time_texts': ['1小时'], 'is_conversation': True},
        ])
        deps = types.SimpleNamespace()
        deps.tab_lock = threading.Lock()
        deps.data_lock = threading.Lock()
        deps.init_global_browser = lambda: FakeBrowser(tab)
        deps.log_to_ui = lambda _level, _msg: None
        deps.save_state_called = 0
        deps.save_state = lambda: setattr(deps, 'save_state_called', deps.save_state_called + 1)
        deps._set_runtime_attr = lambda name, value: setattr(deps, name, value)

        result = rc.scan_recent_dm_contacts_with_browser(deps, max_scrolls=1)

        self.assertTrue(tab.closed)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['contacts'][0]['handle'], '@wangwu')
        self.assertEqual(deps.dm_recent_contacts_result['copy_text'], '@wangwu')
        self.assertEqual(deps.save_state_called, 1)

    def test_seconds_until_daily_run(self):
        now = datetime.datetime(2026, 5, 12, 8, 30, 0)
        self.assertEqual(rc._seconds_until_daily_run(now), 1800)
        after = datetime.datetime(2026, 5, 12, 9, 1, 0)
        self.assertEqual(rc._seconds_until_daily_run(after), 23 * 3600 + 59 * 60)

    def test_previous_daily_window_uses_9am_boundary(self):
        start, end = rc.previous_daily_window(datetime.datetime(2026, 5, 12, 13, 0, 0))
        self.assertEqual(start, datetime.datetime(2026, 5, 11, 9, 0, 0))
        self.assertEqual(end, datetime.datetime(2026, 5, 12, 9, 0, 0))

        early_start, early_end = rc.previous_daily_window(datetime.datetime(2026, 5, 12, 8, 0, 0))
        self.assertEqual(early_start, datetime.datetime(2026, 5, 10, 9, 0, 0))
        self.assertEqual(early_end, datetime.datetime(2026, 5, 11, 9, 0, 0))

    def test_candidate_window_hours_for_daily_window_is_only_scan_buffer(self):
        now = datetime.datetime(2026, 5, 12, 13, 0, 0)
        start = datetime.datetime(2026, 5, 11, 9, 0, 0)

        self.assertEqual(rc.candidate_window_hours_for_daily_window(start, now), 29)

    def test_filter_contacts_by_time_window(self):
        now = datetime.datetime(2026, 5, 12, 13, 0, 0)
        start = datetime.datetime(2026, 5, 11, 9, 0, 0)
        end = datetime.datetime(2026, 5, 12, 9, 0, 0)
        contacts = [
            {'handle': '@old', 'age_seconds': 29 * 3600},
            {'handle': '@in1', 'age_seconds': 27 * 3600},
            {'handle': '@in2', 'age_seconds': 5 * 3600},
            {'handle': '@new', 'age_seconds': 2 * 3600},
            {'handle': '@unknown', 'age_seconds': None},
        ]

        result = rc.filter_contacts_by_time_window(contacts, start=start, end=end, now_fn=lambda: now)

        self.assertEqual([row['handle'] for row in result], ['@in1', '@in2'])

    def test_build_daily_dm_contacts_message(self):
        start = datetime.datetime(2026, 5, 11, 9, 0, 0)
        end = datetime.datetime(2026, 5, 12, 9, 0, 0)

        text = rc.build_daily_dm_contacts_message([{'handle': '@a'}, {'handle': '@b'}], start=start, end=end, title='测试')

        self.assertIn('【测试】昨日 9 点到今日 9 点推特私信统计', text)
        self.assertIn('私信人数：2', text)
        self.assertIn('1. @a', text)
        self.assertIn('2. @b', text)

    def test_push_daily_dm_contacts_report_filters_and_sends(self):
        deps = types.SimpleNamespace()
        deps.enterprise_wechat_webhook_url = 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=abc'
        deps.log_to_ui = lambda _level, _msg: None
        now = datetime.datetime(2026, 5, 12, 13, 0, 0)

        original_scan = rc.scan_recent_dm_contacts_with_browser
        original_send = rc.send_enterprise_wechat_text
        sent = {}
        scan_args = {}
        try:
            def fake_scan(_deps, window_hours=24, max_scrolls=8, run_type='daily_09', log_label=''):
                scan_args.update({
                    'window_hours': window_hours,
                    'max_scrolls': max_scrolls,
                    'run_type': run_type,
                    'log_label': log_label,
                })
                return {
                'status': 'ok',
                'count': 3,
                'contacts': [
                    {'handle': '@in', 'age_seconds': 5 * 3600},
                    {'handle': '@new', 'age_seconds': 2 * 3600},
                    {'handle': '@old', 'age_seconds': 29 * 3600},
                ],
            }

            rc.scan_recent_dm_contacts_with_browser = fake_scan
            rc.send_enterprise_wechat_text = lambda webhook, content: sent.update({'webhook': webhook, 'content': content}) or {'status': 'ok', 'msg': 'sent'}

            result = rc.push_daily_dm_contacts_report(deps, now_fn=lambda: now, title='测试')
        finally:
            rc.scan_recent_dm_contacts_with_browser = original_scan
            rc.send_enterprise_wechat_text = original_send

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['copy_text'], '@in')
        self.assertEqual(result['candidate_window_hours'], 29)
        self.assertEqual(scan_args['window_hours'], 29)
        self.assertIn('昨日 9 点到今日 9 点', scan_args['log_label'])
        self.assertEqual(sent['webhook'], deps.enterprise_wechat_webhook_url)
        self.assertIn('@in', sent['content'])
        self.assertNotIn('@new', sent['content'])
        self.assertNotIn('@old', sent['content'])

    def test_send_enterprise_wechat_text_treats_errcode_zero_as_ok(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb):
                return False

            def read(self):
                return b'{"errcode":0,"errmsg":"ok"}'

        original_urlopen = rc.urllib.request.urlopen
        try:
            rc.urllib.request.urlopen = lambda _req, timeout=20: FakeResponse()
            result = rc.send_enterprise_wechat_text(
                'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=abc',
                'hello',
            )
        finally:
            rc.urllib.request.urlopen = original_urlopen

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['wecom']['errcode'], 0)


if __name__ == '__main__':
    unittest.main()
