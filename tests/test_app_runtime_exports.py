import unittest

import app


class AppRuntimeExportsTests(unittest.TestCase):
    def test_critical_runtime_exports_exist(self):
        expected = [
            'ensure_data_dir',
            'migrate_legacy_state_files',
            'load_state',
            'save_state',
            'save_processed_users',
            'log_to_ui',
            'publish_new_data_event',
            'drain_msg_queue',
            '_build_notify_tts_runtime_payload',
            '_build_notify_server_audio_runtime_payload',
            '_build_twitter_cli_runtime_payload',
            '_get_twitter_cli_status',
            '_fetch_twitter_cli_tweet_detail',
            '_fetch_twitter_cli_user',
            '_enrich_notification_from_twitter_cli',
            '_normalize_notify_tts_config_from_payload',
            '_apply_notify_tts_config',
            'analyze_comment_intent',
            'normalize_content_for_dedupe',
            '_normalize_content_for_filter',
            'should_skip_duplicate_content',
            'scan_persistent_notification_tab',
            'scan_notifications_page',
            '_classify_notification_type',
            '_extract_status_id_candidates_from_text',
            '_ensure_notify_flow_fields',
            '_normalize_notify_flow_stage',
            '_resolve_notify_resume_stage',
            '_split_flow_error',
            'send_notification_reply',
            '_normalize_dm_share_link',
            '_is_link_only_message',
            '_build_dm_message_probes',
            '_get_dm_conversation_text',
            '_conversation_contains_dm_text',
            '_confirm_dm_message_sent',
            '_count_dm_probe_occurrence',
            '_count_dm_sent_markers',
            '_prepare_reply_prompt_guard',
            '_open_dm_editor_for_handle',
            '_run_dm_send_with_recovery',
            '_classify_dm_error_text',
            '_is_dm_closed_error_text',
            '_is_dm_context_or_editor_error_text',
            '_is_dm_context_url',
            '_is_dm_soft_send_error_text',
            '_is_dm_send_fallback_continuable_error',
            '_is_profile_locked_by_alive_process',
            '_auto_cleanup_profile_runtime',
            '_cleanup_stale_profile_singletons',
            'create_browser_user_data_dir',
            'cleanup_browser_user_data_dir',
            'is_persistent_browser_profile_dir',
            '_wait_document_ready',
            'get_browser_path',
            'get_browser_proxy',
            'get_browser_proxy_source',
            'build_browser_proxy_runtime_payload',
            'resolve_server_port',
        ]
        missing = [name for name in expected if not hasattr(app, name)]
        self.assertEqual(missing, [], f'missing exports: {missing}')

    def test_state_endpoint_smoke(self):
        client = app.app.test_client()
        resp = client.get('/api/state')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIsInstance(data, dict)
        for key in [
            'token_configured',
            'tasks',
            'pending',
            'notification_monitoring',
            'delegated_account',
            'headless_mode',
            'notify_reply_templates',
            'dm_message_templates',
            'llm_filter_model',
            'notify_tts_voice_type',
        ]:
            self.assertIn(key, data)
        self.assertIn('llm_filter_api_key_configured', data)
        self.assertNotIn('llm_filter_api_key', data)

    def test_state_endpoint_payload_types(self):
        client = app.app.test_client()
        data = client.get('/api/state').get_json()
        self.assertIsInstance(data['tasks'], list)
        self.assertIsInstance(data['pending'], list)
        self.assertIsInstance(data['notification_monitoring'], bool)
        self.assertIsInstance(data['headless_mode'], bool)
        self.assertIsInstance(data['llm_filter_timeout_max_sec'], float)


if __name__ == '__main__':
    unittest.main()
