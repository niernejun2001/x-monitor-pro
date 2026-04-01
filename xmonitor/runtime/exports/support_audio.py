from xmonitor.services.audio.server_audio import (
    build_notify_server_audio_runtime_payload as _build_notify_server_audio_runtime_payload_impl,
    enqueue_notify_server_audio as _enqueue_notify_server_audio_impl,
    ensure_notify_server_audio_worker as _ensure_notify_server_audio_worker_impl,
)
from xmonitor.services.audio.tts import (
    doubao_tts_is_ready as _doubao_tts_is_ready_impl,
    doubao_tts_mime_by_encoding as _doubao_tts_mime_by_encoding_impl,
    synthesize_doubao_tts_audio_base64 as _synthesize_doubao_tts_audio_base64_impl,
    truncate_text_for_tts as _truncate_text_for_tts_impl,
)
from xmonitor.services.audio.tts_config import (
    apply_notify_tts_config as _apply_notify_tts_config_impl,
    build_notify_tts_runtime_payload as _build_notify_tts_runtime_payload_impl,
    normalize_notify_tts_config_from_payload as _normalize_notify_tts_config_from_payload_impl,
)


def build_support_audio_exports(deps):
    def _build_notify_tts_runtime_payload(include_secrets=True):
        return _build_notify_tts_runtime_payload_impl(deps, include_secrets=include_secrets)

    def _build_notify_server_audio_runtime_payload():
        return _build_notify_server_audio_runtime_payload_impl(deps)

    def _ensure_notify_server_audio_worker():
        return _ensure_notify_server_audio_worker_impl(deps)

    def _enqueue_notify_server_audio(item):
        return _enqueue_notify_server_audio_impl(item, deps)

    def _normalize_notify_tts_config_from_payload(payload):
        return _normalize_notify_tts_config_from_payload_impl(payload, deps)

    def _apply_notify_tts_config(cfg):
        return _apply_notify_tts_config_impl(cfg, deps)

    def _doubao_tts_is_ready():
        return _doubao_tts_is_ready_impl(deps)

    def _doubao_tts_mime_by_encoding(encoding):
        return _doubao_tts_mime_by_encoding_impl(encoding)

    def _truncate_text_for_tts(text):
        return _truncate_text_for_tts_impl(text, deps)

    def _synthesize_doubao_tts_audio_base64(text):
        return _synthesize_doubao_tts_audio_base64_impl(text, deps)

    return {
        '_build_notify_tts_runtime_payload': _build_notify_tts_runtime_payload,
        '_build_notify_server_audio_runtime_payload': _build_notify_server_audio_runtime_payload,
        '_ensure_notify_server_audio_worker': _ensure_notify_server_audio_worker,
        '_enqueue_notify_server_audio': _enqueue_notify_server_audio,
        '_normalize_notify_tts_config_from_payload': _normalize_notify_tts_config_from_payload,
        '_apply_notify_tts_config': _apply_notify_tts_config,
        '_doubao_tts_is_ready': _doubao_tts_is_ready,
        '_doubao_tts_mime_by_encoding': _doubao_tts_mime_by_encoding,
        '_truncate_text_for_tts': _truncate_text_for_tts,
        '_synthesize_doubao_tts_audio_base64': _synthesize_doubao_tts_audio_base64,
    }
