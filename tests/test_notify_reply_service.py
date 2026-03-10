import threading
import types
import unittest

from xmonitor.services.notify_reply_service import send_notification_reply


class NotifyReplyServiceTests(unittest.TestCase):
    def test_reuses_cached_generated_dm_text_on_resume(self):
        supplier_results = []
        llm_calls = []
        flow_updates = []

        class FakeNotifyFacade:
            def find_pending_item_by_key(self, key):
                return 0, {
                    'key': key,
                    'source': '通知页面',
                    'handle': '@demo',
                    'notify_flow_stage': 'share_link_ready',
                    'notify_share_link': 'https://x.com/demo/status/1',
                    'notify_dm_text_generated': '缓存好的第二条私信文案',
                    'notify_dm_llm_used': True,
                    'notify_dm_llm_latency_ms': 321,
                    'notify_dm_llm_regen_attempt': 1,
                }

            def update_flow_state(self, key, stage='', error='', retry_at=0.0, extra=None, save=False):
                flow_updates.append((key, stage, extra or {}))
                return True

        def stage_at_least(current, target):
            order = {
                'reply_pending': 10,
                'match_card': 20,
                'share_link_ready': 30,
                'reply_sent': 40,
                'dm_opening': 50,
                'dm_link_sent': 60,
                'dm_text_generating': 65,
                'dm_text_sent': 70,
                'done': 90,
            }
            return order.get(str(current or ''), 0) >= order.get(str(target or ''), 0)

        def fake_run_dm_send_with_recovery(tab, dm_handle, share_link, dm_text, mark_func=None, best_effort=False, progress=None, dm_text_supplier=None):
            self.assertEqual(dm_handle, '@demo')
            self.assertEqual(share_link, 'https://x.com/demo/status/1')
            self.assertEqual(dm_text, '模板文案')
            self.assertIsNotNone(dm_text_supplier)
            supplier_results.append(dm_text_supplier())
            supplier_results.append(dm_text_supplier())
            return True, '', False, tab

        deps = types.SimpleNamespace(
            global_token='token',
            extract_status_id_from_notification_item=lambda item: '1234567890123456789',
            reply_action_lock=threading.Lock(),
            _throttle_reply_action_if_needed=lambda: None,
            _set_reply_flow_active=lambda active: None,
            notify_state_facade=FakeNotifyFacade(),
            ensure_reply_work_tab=lambda: types.SimpleNamespace(url='https://x.com/notifications', get=lambda url: None),
            _prepare_reply_prompt_guard=lambda tab, stage='': None,
            log_to_ui=lambda level, msg: None,
            _resolve_notify_resume_stage=lambda row: str(row.get('notify_flow_stage') or 'reply_pending'),
            _normalize_dm_share_link=lambda raw, status_id='', status_handle='', fallback_url='': str(raw or fallback_url or ''),
            _get_status_link_from_item=lambda item, matched_handle='', matched_status_id='': 'https://x.com/demo/status/1',
            _notify_stage_at_least=stage_at_least,
            _reply_humanized_idle=lambda tab, low=0.0, high=0.0, stage='': None,
            _prepare_notifications_view_impl=lambda tab, deps, force_refresh=False: None,
            _match_target_card_impl=lambda tab, item, status_id, deps: (None, None, 0, '', '', ''),
            _send_reply_from_button_impl=lambda tab, target_reply_btn, target_score, reply_text, status_id, handle_hint, deps: (True, ''),
            _sanitize_dm_message_text=lambda text: str(text or '').strip(),
            dm_message_templates=[],
            DM_FOLLOWUP_TEXT='模板文案',
            DM_LLM_REWRITE_ENABLED=True,
            _generate_dm_text_with_llm=lambda template_text: (llm_calls.append(template_text) or (True, '新生成文案', {'llm_used': True, 'latency_ms': 1, 'regen_attempt': 1})),
            _should_use_share_link_quick_path=lambda: False,
            _reserve_notify_dm_user_slot=lambda handle, task_key='': (True, 0.0),
            normalize_handle=lambda h: str(h or '').strip().lstrip('@').lower(),
            _run_dm_send_with_recovery=fake_run_dm_send_with_recovery,
            DM_CLOSED_FALLBACK_REPLY_TEXT='fallback',
            _wait_document_ready=lambda tab, timeout=5.0: None,
            _is_unhandled_prompt_error=lambda err: False,
            _capture_runtime_diagnostic=lambda *args, **kwargs: '',
        )

        ok, err = send_notification_reply(
            {'key': 'n1', 'handle': '@demo', 'status_handle': '@demo'},
            '公开回复',
            deps,
            dm_message='模板文案',
        )

        self.assertTrue(ok)
        self.assertEqual(err, '')
        self.assertEqual(llm_calls, [])
        self.assertEqual(len(supplier_results), 2)
        self.assertEqual(supplier_results[0][1], '缓存好的第二条私信文案')
        self.assertEqual(supplier_results[1][1], '缓存好的第二条私信文案')
        self.assertTrue(any(stage == 'done' for _, stage, _ in flow_updates))


if __name__ == '__main__':
    unittest.main()
