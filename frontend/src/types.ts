export interface TaskItem {
  url: string
  last_check?: string
}

export interface PendingItem {
  key: string
  source: string
  handle?: string
  content?: string
  time?: string
  status_id?: string
  status_handle?: string
  status_url?: string
  notification_type?: string
  notification_text?: string
  notification_age_minutes?: number | null
  intent_score?: number
  intent_level?: string
  is_intent_user?: boolean
  force_notify?: boolean
  llm_used?: boolean
  intent_reason?: string
  intent_signals?: string[]
  voice_should_notify?: boolean
  notify_reply_text?: string
  notify_dm_text?: string
  notify_dm_text_generated?: string
  notify_dm_llm_used?: boolean
  notify_dm_llm_error_code?: string
  notify_dm_llm_error_detail?: string
  notify_replied?: boolean
  reply_checked?: boolean
  notify_reply_time?: string
  reply_time?: string
  notify_flow_stage?: string
  notify_flow_error_code?: string
  notify_flow_error_detail?: string
  notify_flow_error?: string
  notify_retry_time?: string
  notify_flow_attempt?: number
  [key: string]: unknown
}

export interface DmRecentContact {
  name: string
  handle: string
  raw_text?: string
  age_seconds?: number | null
  age_text?: string
  captured_at?: string
}

export interface DmRecentContactsPayload {
  status: string
  msg?: string
  contacts: DmRecentContact[]
  count: number
  copy_text: string
  scanned_rows?: number
  stale_rows?: number
  unknown_time_rows?: number
  window_hours?: number
  source_url?: string
  captured_at?: string
  next_run_at?: number
  last_error?: string
  last_run_type?: string
}

export interface NotificationScheduleSnapshot {
  period_label?: string
  boost_active?: boolean
  idle_active?: boolean
  scan_multiplier?: number
  refresh_multiplier?: number
  idle_scan_streak?: number
  boost_age_sec?: number | null
}

export interface StatePayload {
  token?: string
  token_configured?: boolean
  tasks: TaskItem[]
  is_running: boolean
  pending: PendingItem[]
  updates_last_seq: number
  updates_buffer_size: number
  notification_monitoring: boolean
  notification_schedule_snapshot?: NotificationScheduleSnapshot
  notification_schedule_text?: string
  notification_refresh_interval?: number
  notification_last_refresh_at?: number
  notification_next_refresh_at?: number
  notification_scan_interval?: number
  notification_last_scan_at?: number
  notification_next_scan_at?: number
  notification_last_new_item_at?: number
  notification_idle_scan_streak?: number
  notification_full_refresh_pending?: boolean
  notification_full_refresh_reason?: string
  notification_dm_light_scan_count?: number
  dm_recent_contacts?: DmRecentContactsPayload
  delegated_account: string
  delegated_enabled: boolean
  enterprise_wechat_webhook_url?: string
  headless_mode: boolean
  notify_reply_templates: string[]
  dm_message_templates: string[]
  llm_filter_enabled: boolean
  llm_filter_base_url: string
  llm_filter_api_key_configured?: boolean
  llm_filter_model: string
  llm_filter_timeout_sec: number
  llm_filter_timeout_max_sec: number
  llm_filter_retry_count?: number
  llm_filter_retry_backoff_sec?: number
  llm_filter_prompt_template: string
  llm_intent_prompt_template: string
  dm_llm_rewrite_enabled: boolean
  dm_llm_rewrite_prompt_template: string
  dm_llm_rewrite_max_chars: number
  dm_llm_rewrite_temperature: number
  dm_llm_rewrite_max_regen: number
  dm_llm_rewrite_dedupe_size: number
  notify_voice_block_keywords_text: string
  notification_reply_only_mode: boolean
  notify_tts_enabled?: boolean
  notify_tts_ready?: boolean
  notify_tts_provider?: string
  notify_tts_app_id?: string
  notify_tts_access_token_configured?: boolean
  notify_tts_secret_key_configured?: boolean
  notify_tts_voice_type?: string
  notify_tts_cluster?: string
  notify_tts_endpoint?: string
  notify_tts_uid?: string
  notify_tts_encoding?: string
  notify_tts_speed_ratio?: number
  notify_tts_volume_ratio?: number
  notify_tts_pitch_ratio?: number
  notify_tts_timeout_sec?: number
  notify_tts_text_max_chars?: number
  notify_server_audio_enabled?: boolean
  notify_server_audio_ready?: boolean
  notify_server_audio_player?: string
  notify_server_audio_last_error?: string
  notify_server_audio_last_ok_at?: number
  notify_server_audio_queue_size?: number
  browser_proxy_configured?: boolean
  browser_proxy_source?: string
  browser_proxy_display?: string
  twitter_cli_enabled?: boolean
  twitter_cli_available?: boolean
  twitter_cli_import_error?: string
  twitter_cli_last_error?: string
}
