import datetime
import unittest
from unittest import mock

from xmonitor.services.notify.scan_helpers import (
    extract_notification_handle,
    parse_notification_age_minutes,
)


class _Article:
    def __init__(self, user_text='', hrefs=None, time_text='', time_datetime='', html=''):
        self._user_text = user_text
        self._hrefs = list(hrefs or [])
        self._time_text = time_text
        self._time_datetime = time_datetime
        self.html = html

    def ele(self, selector, timeout=0):
        if selector == 'css:[data-testid="User-Name"]' and self._user_text:
            return type('UserEle', (), {'text': self._user_text})()
        if selector == 'tag:time' and (self._time_text or self._time_datetime):
            return type(
                'TimeEle',
                (),
                {
                    'text': self._time_text,
                    'attr': lambda self, name, _dt=self._time_datetime: _dt if name == 'datetime' else '',
                },
            )()
        raise Exception('not found')

    def eles(self, selector, timeout=0):
        if selector != 'tag:a':
            return []
        out = []
        for href in self._hrefs:
            out.append(type('LinkEle', (), {'attr': lambda self, name, _href=href: _href if name == 'href' else ''})())
        return out


class NotificationScanHelpersTests(unittest.TestCase):
    def test_extract_notification_handle_ignores_email_like_text(self):
        article = _Article()
        text = '18295025596mike@gmai @18295025596mike · 27秒 回复 @manateelazycat 1'

        handle = extract_notification_handle(article, text)

        self.assertEqual(handle, '@18295025596mike')

    def test_extract_notification_handle_prefers_user_name_block(self):
        article = _Article(user_text='Some Name\n@RealUser')

        handle = extract_notification_handle(article, 'test@example.com hello @fallback')

        self.assertEqual(handle, '@RealUser')

    def test_extract_notification_handle_uses_profile_link_when_available(self):
        article = _Article(hrefs=['/demo_user/status/1234567890'])

        handle = extract_notification_handle(article, '')

        self.assertEqual(handle, '@demo_user')

    def test_extract_notification_handle_supports_absolute_profile_link(self):
        article = _Article(hrefs=['https://x.com/demo_user/status/1234567890'])

        handle = extract_notification_handle(article, '')

        self.assertEqual(handle, '@demo_user')

    def test_extract_notification_handle_supports_legacy_statuses_path(self):
        article = _Article(hrefs=['https://mobile.twitter.com/demo_user/statuses/1234567890'])

        handle = extract_notification_handle(article, '')

        self.assertEqual(handle, '@demo_user')

    def test_extract_notification_handle_uses_profile_photo_link_when_available(self):
        article = _Article(hrefs=['/demo_user/photo'])

        handle = extract_notification_handle(article, '')

        self.assertEqual(handle, '@demo_user')

    def test_extract_notification_handle_falls_back_to_html_hrefs(self):
        article = _Article(html='<div><a href="/demo_user/photo"></a></div>')

        handle = extract_notification_handle(article, '')

        self.assertEqual(handle, '@demo_user')

    def test_extract_notification_handle_falls_back_to_absolute_html_hrefs(self):
        article = _Article(html='<div><a href="https://twitter.com/demo_user/photo"></a></div>')

        handle = extract_notification_handle(article, '')

        self.assertEqual(handle, '@demo_user')

    def test_parse_notification_age_minutes_supports_relative_units(self):
        self.assertEqual(parse_notification_age_minutes(_Article(time_text='5m')), 5)
        self.assertEqual(parse_notification_age_minutes(_Article(time_text='2h')), 120)
        self.assertEqual(parse_notification_age_minutes(_Article(time_text='3d')), 4320)
        self.assertEqual(parse_notification_age_minutes(_Article(time_text='2 weeks')), 20160)
        self.assertEqual(parse_notification_age_minutes(_Article(time_text='1mo')), 43200)
        self.assertEqual(parse_notification_age_minutes(_Article(time_text='刚刚')), 0)

    def test_parse_notification_age_minutes_prefers_datetime_attr(self):
        article = _Article(time_text='5m', time_datetime='2026-04-07T00:00:00+00:00')
        age = parse_notification_age_minutes(article)
        self.assertIsNotNone(age)
        self.assertGreaterEqual(age, 0)

    def test_parse_notification_age_minutes_supports_absolute_english_dates(self):
        class _FakeDateTime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 4, 7, 12, 0, 0, tzinfo=tz or datetime.timezone.utc)

        article = _Article(time_text='Apr 6')
        with mock.patch('xmonitor.services.notify.scan_helpers.datetime.datetime', _FakeDateTime):
            age = parse_notification_age_minutes(article)
        self.assertEqual(age, 2160)

    def test_parse_notification_age_minutes_supports_absolute_chinese_dates(self):
        class _FakeDateTime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 4, 7, 12, 0, 0, tzinfo=tz or datetime.timezone.utc)

        article = _Article(time_text='4月6日')
        with mock.patch('xmonitor.services.notify.scan_helpers.datetime.datetime', _FakeDateTime):
            age = parse_notification_age_minutes(article)
        self.assertEqual(age, 2160)

    def test_parse_notification_age_minutes_supports_numeric_dates(self):
        class _FakeDateTime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 4, 7, 12, 0, 0, tzinfo=tz or datetime.timezone.utc)

        with mock.patch('xmonitor.services.notify.scan_helpers.datetime.datetime', _FakeDateTime):
            self.assertEqual(parse_notification_age_minutes(_Article(time_text='2026-04-06')), 2160)
            self.assertEqual(parse_notification_age_minutes(_Article(time_text='4/6')), 2160)

    def test_parse_notification_age_minutes_supports_yesterday(self):
        self.assertEqual(parse_notification_age_minutes(_Article(time_text='yesterday')), 1440)
        self.assertEqual(parse_notification_age_minutes(_Article(time_text='昨天')), 1440)


if __name__ == '__main__':
    unittest.main()
