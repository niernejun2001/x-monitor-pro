        const tableBodyIds = { notify: 'notifyTableBody', tweet: 'tweetTableBody' };
        const filterInputIds = { notify: 'notifyFilterInput', tweet: 'tweetFilterInput' };
        const filterOptionIds = { notify: 'notifyFilterOptions', tweet: 'tweetFilterOptions' };
        let notifyReplyTemplates = [];
        let dmMessageTemplates = [];
        const templateEditState = { reply: -1, dm: -1 };
        const notifyVoiceText = '';
        let lastNotifyVoiceAt = 0;
        let cachedNotifyVoice = null;
        let notifyVoicePlaying = false;
        let notifyVoiceTimer = null;
        const notifyVoiceQueue = [];
        const notifyIntentQueue = [];
        let notifyIntentBusy = false;
        let notifyRowSeq = 0;
        let notifyVoiceBlockKeywords = [];
        let notifyTtsProvider = 'doubao';
        let notifyTtsReady = false;
        let notifyTtsVoiceType = '';
        let notifyBackendAudio = null;
        let notifyBrowserUtterance = null;
        let notifyAudioContext = null;
        let notifyAudioGainNode = null;
        let notifyAudioCompressorNode = null;
        let notifyAudioSourceNode = null;
        let notifyAudioBufferSource = null;
        let notifyAudioUnlocked = false;
        const NOTIFY_AUDIO_GAIN_KEY = 'xmonitor_notify_audio_gain_v1';
        const NOTIFY_AUDIO_GAIN_DEFAULT = 5.0;
        let notifyAudioGainValue = NOTIFY_AUDIO_GAIN_DEFAULT;
        const NOTIFY_AUDIO_DIAG_ENDPOINT = '/api/debug/notify_audio';
        const NOTIFY_TABLE_HEIGHT_KEY = 'xmonitor_notify_table_height_v1';
        let llmTimeoutMaxSec = 120;
        let updatesLastSeq = 0;
        let updatesPollFailStreak = 0;
        let updatesRecoverCoolUntil = 0;

        function clampNotifyAudioGain(raw) {
            const v = Number(raw);
            if(!Number.isFinite(v)) return NOTIFY_AUDIO_GAIN_DEFAULT;
            return Math.max(1.0, Math.min(12.0, Math.round(v * 10) / 10));
        }

        function applyNotifyAudioGainUi() {
            const range = document.getElementById('notifyAudioGainRange');
            const label = document.getElementById('notifyAudioGainValue');
            const gain = clampNotifyAudioGain(notifyAudioGainValue);
            if(range) range.value = gain.toFixed(1);
            if(label) label.textContent = `${gain.toFixed(1)}x`;
            if (notifyAudioGainNode) {
                notifyAudioGainNode.gain.value = gain;
            }
        }

        function setNotifyAudioGain(raw, persist = true) {
            notifyAudioGainValue = clampNotifyAudioGain(raw);
            applyNotifyAudioGainUi();
            if (persist) {
                try { localStorage.setItem(NOTIFY_AUDIO_GAIN_KEY, notifyAudioGainValue.toFixed(1)); } catch (_) {}
            }
        }

        function restoreNotifyAudioGain() {
            let stored = '';
            try { stored = localStorage.getItem(NOTIFY_AUDIO_GAIN_KEY) || ''; } catch (_) { stored = ''; }
            if (stored) {
                setNotifyAudioGain(stored, false);
                return;
            }
            setNotifyAudioGain(NOTIFY_AUDIO_GAIN_DEFAULT, false);
        }

        function bindNotifyAudioGainControl() {
            const range = document.getElementById('notifyAudioGainRange');
            if (!range) return;
            range.addEventListener('input', () => setNotifyAudioGain(range.value, false));
            range.addEventListener('change', () => setNotifyAudioGain(range.value, true));
        }
        function clampNotifyTableHeight(rawHeight) {
            const minHeight = 220;
            const maxHeight = Math.max(280, Math.floor(window.innerHeight * 0.75));
            const h = Number(rawHeight || 0);
            if(!Number.isFinite(h) || h <= 0) return 280;
            return Math.max(minHeight, Math.min(maxHeight, Math.round(h)));
        }

        function getNotifyTableContainer() {
            return document.getElementById('notifyTableContainer');
        }

        function saveNotifyTableHeight() {
            const container = getNotifyTableContainer();
            if(!container) return;
            const height = clampNotifyTableHeight(container.getBoundingClientRect().height);
            try {
                localStorage.setItem(NOTIFY_TABLE_HEIGHT_KEY, String(height));
            } catch (_) {}
        }

        function restoreNotifyTableHeight() {
            const container = getNotifyTableContainer();
            if(!container) return;
            let stored = '';
            try {
                stored = localStorage.getItem(NOTIFY_TABLE_HEIGHT_KEY) || '';
            } catch (_) {
                stored = '';
            }
            if(!stored) return;
            const height = clampNotifyTableHeight(parseInt(stored, 10));
            container.style.height = `${height}px`;
        }

        function bindNotifyTableHeightPersistence() {
            const container = getNotifyTableContainer();
            if(!container) return;
            restoreNotifyTableHeight();

            if('ResizeObserver' in window) {
                let timer = null;
                const observer = new ResizeObserver(() => {
                    if(timer) clearTimeout(timer);
                    timer = setTimeout(() => saveNotifyTableHeight(), 120);
                });
                observer.observe(container);
            } else {
                container.addEventListener('mouseup', () => setTimeout(() => saveNotifyTableHeight(), 120));
                container.addEventListener('touchend', () => setTimeout(() => saveNotifyTableHeight(), 120));
            }

            window.addEventListener('beforeunload', saveNotifyTableHeight);
            window.addEventListener('resize', () => {
                const el = getNotifyTableContainer();
                if(!el) return;
                if(!el.style.height) return;
                el.style.height = `${clampNotifyTableHeight(parseInt(el.style.height, 10))}px`;
                saveNotifyTableHeight();
            });
        }

        function parseKeywordLines(rawText) {
            const parts = String(rawText || '').split(/[\n,，;；]+/g);
            const out = [];
            const seen = new Set();
            parts.forEach(part => {
                const kw = String(part || '').trim();
                if(!kw) return;
                const low = kw.toLowerCase();
                if(seen.has(low)) return;
                seen.add(low);
                out.push(kw);
            });
            return out;
        }

        function refreshNotifyVoiceBlockKeywordsFromInput() {
            const el = document.getElementById('notifyVoiceBlockKeywords');
            notifyVoiceBlockKeywords = parseKeywordLines(el ? el.value : '');
        }

        function shouldSuppressNotifyVoice(contentText) {
            refreshNotifyVoiceBlockKeywordsFromInput();
            const text = String(contentText || '').toLowerCase();
            if(!text || !notifyVoiceBlockKeywords.length) return false;
            return notifyVoiceBlockKeywords.some(kw => text.includes(String(kw || '').toLowerCase()));
        }

        function pickNotifyVoice() {
            if (!('speechSynthesis' in window)) return null;
            const voices = window.speechSynthesis.getVoices() || [];
            if (!voices.length) return null;

            const femaleKeys = ['female', 'woman', 'girl', '女', 'xiaoxiao', 'xiaoyi', 'xiaohan', 'xiaomo', 'tingting', 'siri'];
            const zhVoices = voices.filter(v => (v.lang || '').toLowerCase().includes('zh'));
            const scored = (zhVoices.length ? zhVoices : voices).map(v => {
                const name = `${v.name || ''} ${(v.lang || '')}`.toLowerCase();
                let score = 0;
                if ((v.lang || '').toLowerCase().includes('zh-cn')) score += 6;
                if ((v.lang || '').toLowerCase().includes('zh')) score += 3;
                if (femaleKeys.some(k => name.includes(k))) score += 8;
                if ((v.name || '').toLowerCase().includes('natural')) score += 2;
                return { v, score };
            }).sort((a, b) => b.score - a.score);
            return scored.length ? scored[0].v : null;
        }

        function preloadNotifyVoice() {
            cachedNotifyVoice = pickNotifyVoice();
        }

        function buildNotifyVoiceText(contentText='') {
            const raw = String(contentText || '').replace(/\s+/g, ' ').trim();
            const prefix = `${notifyVoiceText ? `${notifyVoiceText},` : ''}评论内容：`;
            if(!raw) return prefix;
            const maxLen = 80;
            const clipped = raw.length > maxLen ? `${raw.slice(0, maxLen)}...` : raw;
            return `${prefix}${clipped}`;
        }

        function _getOrCreateNotifyAudioContext() {
            const AudioCtx = window.AudioContext || window.webkitAudioContext;
            if (!AudioCtx) return null;
            if (!notifyAudioContext) {
                notifyAudioContext = new AudioCtx();
            }
            if (!notifyAudioGainNode) {
                notifyAudioGainNode = notifyAudioContext.createGain();
            }
            if (!notifyAudioCompressorNode && typeof notifyAudioContext.createDynamicsCompressor === 'function') {
                notifyAudioCompressorNode = notifyAudioContext.createDynamicsCompressor();
                notifyAudioCompressorNode.threshold.value = -20;
                notifyAudioCompressorNode.knee.value = 18;
                notifyAudioCompressorNode.ratio.value = 5;
                notifyAudioCompressorNode.attack.value = 0.003;
                notifyAudioCompressorNode.release.value = 0.2;
            }
            try { notifyAudioGainNode.disconnect(); } catch (_) {}
            if (notifyAudioCompressorNode) {
                try { notifyAudioCompressorNode.disconnect(); } catch (_) {}
                notifyAudioGainNode.connect(notifyAudioCompressorNode);
                notifyAudioCompressorNode.connect(notifyAudioContext.destination);
            } else {
                notifyAudioGainNode.connect(notifyAudioContext.destination);
            }
            notifyAudioGainNode.gain.value = clampNotifyAudioGain(notifyAudioGainValue);
            return notifyAudioContext;
        }

        function _getNotifyAudioCtxState() {
            const ctx = notifyAudioContext;
            if (!ctx) return 'none';
            return String(ctx.state || 'unknown');
        }

        function _notifyAudioDiag(stage, details = null) {
            const payload = {
                stage: String(stage || ''),
                details: details && typeof details === 'object' ? details : { message: String(details || '') },
                ts: Date.now(),
            };
            try { console.debug('[NotifyAudioDiag]', payload); } catch (_) {}
            try {
                fetch(NOTIFY_AUDIO_DIAG_ENDPOINT, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                    keepalive: true,
                }).catch(() => {});
            } catch (_) {}
        }

        function unlockNotifyAudioByGesture() {
            const ctx = _getOrCreateNotifyAudioContext();
            if (!ctx) return Promise.resolve(false);
            const kick = () => {
                try {
                    const osc = ctx.createOscillator();
                    const gain = ctx.createGain();
                    gain.gain.value = 0.00001;
                    osc.connect(gain);
                    gain.connect(ctx.destination);
                    osc.start();
                    osc.stop(ctx.currentTime + 0.01);
                } catch (_) {}
                notifyAudioUnlocked = true;
                _notifyAudioDiag('unlock_kick', { ctx_state: _getNotifyAudioCtxState() });
                return true;
            };
            if (ctx.state === 'running') {
                _notifyAudioDiag('unlock_running', { ctx_state: _getNotifyAudioCtxState() });
                return Promise.resolve(kick());
            }
            _notifyAudioDiag('unlock_resume_try', { ctx_state: _getNotifyAudioCtxState() });
            return ctx.resume().then(() => kick()).catch((e) => {
                _notifyAudioDiag('unlock_resume_fail', {
                    ctx_state: _getNotifyAudioCtxState(),
                    err: String((e && (e.message || e.name)) || e || 'unknown'),
                });
                return false;
            });
        }

        function _base64ToArrayBuffer(b64) {
            const binary = atob(String(b64 || ''));
            const len = binary.length;
            const bytes = new Uint8Array(len);
            for (let i = 0; i < len; i += 1) {
                bytes[i] = binary.charCodeAt(i);
            }
            return bytes.buffer;
        }

        function _decodeAudioBuffer(ctx, arrBuf) {
            return new Promise((resolve, reject) => {
                try {
                    const maybe = ctx.decodeAudioData(arrBuf, resolve, reject);
                    if (maybe && typeof maybe.then === 'function') {
                        maybe.then(resolve).catch(reject);
                    }
                } catch (e) {
                    reject(e);
                }
            });
        }

        function _playNotifyPromptChime(done = null) {
            const finish = _onceNotifyDone(done);
            const ctx = _getOrCreateNotifyAudioContext();
            if (!ctx) {
                finish(true);
                return;
            }

            const playNow = () => {
                try {
                    const now = ctx.currentTime + 0.01;
                    const notes = [
                        { f: 880, d: 0.10, delay: 0.00 },  // ding
                        { f: 660, d: 0.14, delay: 0.14 },  // dong
                    ];
                    notes.forEach((n) => {
                        const osc = ctx.createOscillator();
                        const gain = ctx.createGain();
                        osc.type = 'sine';
                        osc.frequency.setValueAtTime(n.f, now + n.delay);
                        const attack = now + n.delay;
                        const release = attack + n.d;
                        gain.gain.setValueAtTime(0.0001, attack);
                        gain.gain.exponentialRampToValueAtTime(0.06, attack + 0.01);
                        gain.gain.exponentialRampToValueAtTime(0.0001, release);
                        osc.connect(gain);
                        gain.connect(notifyAudioGainNode || ctx.destination);
                        osc.start(attack);
                        osc.stop(release + 0.01);
                    });
                    setTimeout(() => finish(true), 340);
                } catch (e) {
                    _notifyAudioDiag('prompt_chime_fail', {
                        err: String((e && (e.message || e.name)) || e || 'unknown'),
                        ctx_state: _getNotifyAudioCtxState(),
                    });
                    finish(false, '提示音播放失败');
                }
            };

            if (ctx.state === 'suspended') {
                ctx.resume().then(() => playNow()).catch(() => finish(false, '音频上下文未解锁'));
                return;
            }
            playNow();
        }

        function _playNotifyVoiceByWebAudioData(audioBase64, done = null) {
            const finish = _onceNotifyDone(done);
            const ctx = _getOrCreateNotifyAudioContext();
            if (!ctx) {
                _notifyAudioDiag('webaudio_no_ctx');
                finish(false, '浏览器不支持 WebAudio 播放');
                return;
            }
            const playDecoded = () => {
                let arrBuf = null;
                try {
                    arrBuf = _base64ToArrayBuffer(audioBase64);
                } catch (_) {
                    _notifyAudioDiag('webaudio_b64_decode_fail');
                    finish(false, '音频数据解码失败');
                    return;
                }
                _decodeAudioBuffer(ctx, arrBuf).then(buffer => {
                    _notifyAudioDiag('webaudio_decoded', {
                        ctx_state: _getNotifyAudioCtxState(),
                        duration: Number(buffer.duration || 0).toFixed(3),
                        channels: buffer.numberOfChannels || 0,
                        sample_rate: buffer.sampleRate || 0,
                    });
                    if (notifyAudioBufferSource) {
                        try { notifyAudioBufferSource.stop(0); } catch (_) {}
                        try { notifyAudioBufferSource.disconnect(); } catch (_) {}
                        notifyAudioBufferSource = null;
                    }
                    const src = ctx.createBufferSource();
                    src.buffer = buffer;
                    src.connect(notifyAudioGainNode);
                    src.onended = () => {
                        if (notifyAudioBufferSource === src) notifyAudioBufferSource = null;
                        _notifyAudioDiag('webaudio_end', { ctx_state: _getNotifyAudioCtxState() });
                        finish(true);
                    };
                    notifyAudioBufferSource = src;
                    src.start(0);
                    _notifyAudioDiag('webaudio_start', { ctx_state: _getNotifyAudioCtxState() });
                }).catch(() => {
                    _notifyAudioDiag('webaudio_decode_fail', { ctx_state: _getNotifyAudioCtxState() });
                    finish(false, 'WebAudio 解码播放失败');
                });
            };
            if (ctx.state === 'suspended') {
                _notifyAudioDiag('webaudio_resume_try', { ctx_state: _getNotifyAudioCtxState() });
                ctx.resume().then(() => playDecoded()).catch((e) => {
                    _notifyAudioDiag('webaudio_resume_fail', {
                        ctx_state: _getNotifyAudioCtxState(),
                        err: String((e && (e.message || e.name)) || e || 'unknown'),
                    });
                    finish(false, '音频上下文未解锁，请先点击页面');
                });
                return;
            }
            playDecoded();
        }
        function _onceNotifyDone(done = null) {
            let called = false;
            return function(ok = true, msg = '') {
                if(called) return;
                called = true;
                if (typeof done === 'function') done(ok, msg);
            };
        }

        function _stopNotifyBackendAudio() {
            if (notifyAudioBufferSource) {
                try { notifyAudioBufferSource.stop(0); } catch (_) {}
                try { notifyAudioBufferSource.disconnect(); } catch (_) {}
                notifyAudioBufferSource = null;
            }
            if(notifyAudioSourceNode) {
                try { notifyAudioSourceNode.disconnect(); } catch (_) {}
                notifyAudioSourceNode = null;
            }
            if(!notifyBackendAudio) return;
            try {
                notifyBackendAudio.onended = null;
                notifyBackendAudio.onerror = null;
                notifyBackendAudio.pause();
                notifyBackendAudio.src = '';
            } catch (_) {}
            notifyBackendAudio = null;
        }

        function _stopNotifyBrowserSpeech() {
            if(!('speechSynthesis' in window)) return;
            try {
                if(notifyBrowserUtterance) {
                    notifyBrowserUtterance.onend = null;
                    notifyBrowserUtterance.onerror = null;
                    notifyBrowserUtterance = null;
                }
                window.speechSynthesis.cancel();
            } catch (_) {}
        }

        function stopNotifyVoicePlayback() {
            if (notifyVoiceTimer) {
                clearTimeout(notifyVoiceTimer);
                notifyVoiceTimer = null;
            }
            _stopNotifyBackendAudio();
            _stopNotifyBrowserSpeech();
        }

        function _playNotifyVoiceByAudioData(audioBase64, mime, done = null) {
            const finish = _onceNotifyDone(done);
            const b64 = String(audioBase64 || '').trim();
            if(!b64) {
                _notifyAudioDiag('play_b64_empty');
                finish(false, '豆包返回音频为空');
                return;
            }
            _notifyAudioDiag('play_recv_audio', {
                b64_len: b64.length,
                mime: String(mime || 'audio/mpeg'),
                ctx_state: _getNotifyAudioCtxState(),
                unlocked: !!notifyAudioUnlocked,
            });
            try {
                _stopNotifyBrowserSpeech();
                _stopNotifyBackendAudio();
                const playSpeech = () => {
                    const ctx = _getOrCreateNotifyAudioContext();
                    if (ctx) {
                        _notifyAudioDiag('play_webaudio_primary', { ctx_state: _getNotifyAudioCtxState() });
                        _playNotifyVoiceByWebAudioData(b64, (ok, msg) => {
                            if (ok) {
                                finish(true);
                                return;
                            }
                            _notifyAudioDiag('play_webaudio_primary_fail', {
                                ctx_state: _getNotifyAudioCtxState(),
                                err: String(msg || 'unknown'),
                            });
                            finish(false, msg || 'WebAudio播放失败');
                        });
                        return;
                    }
                    const safeMime = String(mime || 'audio/mpeg').trim() || 'audio/mpeg';
                    const src = `data:${safeMime};base64,${b64}`;
                    const audio = new Audio(src);
                    notifyBackendAudio = audio;
                    audio.volume = 1.0;
                    audio.onended = () => {
                        if(notifyBackendAudio === audio) notifyBackendAudio = null;
                        finish(true);
                    };
                    audio.onerror = () => {
                        if(notifyBackendAudio === audio) notifyBackendAudio = null;
                        finish(false, '浏览器音频播放错误');
                    };
                    const p = audio.play();
                    if (p && typeof p.then === 'function') {
                        p.catch((e) => {
                            const blocked = e && (e.name === 'NotAllowedError' || /notallowed/i.test(String(e.message || '')));
                            _notifyAudioDiag('play_htmlaudio_reject', {
                                err: String((e && (e.message || e.name)) || e || 'unknown'),
                                blocked: !!blocked,
                            });
                            if(notifyBackendAudio === audio) notifyBackendAudio = null;
                            finish(false, blocked ? '浏览器阻止音频播放，请检查页面是否静音或自动播放策略' : '浏览器音频播放失败');
                        });
                    }
                };

                _playNotifyPromptChime((chimeOk, chimeMsg) => {
                    if (!chimeOk) {
                        _notifyAudioDiag('prompt_chime_skip', { msg: String(chimeMsg || 'unknown') });
                    } else {
                        _notifyAudioDiag('prompt_chime_ok');
                    }
                    setTimeout(playSpeech, 30);
                });
            } catch (_) {
                _stopNotifyBackendAudio();
                _notifyAudioDiag('play_init_fail');
                finish(false, '浏览器音频组件初始化失败');
            }
        }

        function _playNotifyVoiceByDoubao(contentText = '', done = null) {
            const speakText = buildNotifyVoiceText(contentText);
            _notifyAudioDiag('doubao_fetch_start', {
                text_len: speakText.length,
                provider: notifyTtsProvider,
                ready: !!notifyTtsReady,
            });
            const controller = ('AbortController' in window) ? new AbortController() : null;
            const timer = setTimeout(() => {
                try {
                    if(controller) controller.abort();
                } catch (_) {}
            }, 10000);
            fetch('/api/tts/synthesize', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({text: speakText, source: 'notify_voice'}),
                signal: controller ? controller.signal : undefined,
            }).then(r => r.json()).then(d => {
                if(d.status !== 'ok' || !d.audio_base64) {
                    const errMsg = String(d.msg || d.error || '').trim() || '豆包TTS返回失败';
                    _notifyAudioDiag('doubao_fetch_fail', { err: errMsg, status: String(d.status || '') });
                    if (typeof done === 'function') done(false, errMsg);
                    return;
                }
                _notifyAudioDiag('doubao_fetch_ok', {
                    audio_len: String(d.audio_base64 || '').length,
                    mime: String(d.mime || ''),
                    voice_type: String(d.voice_type || ''),
                });
                _playNotifyVoiceByAudioData(d.audio_base64, d.mime || 'audio/mpeg', done);
            }).catch((e) => {
                const errMsg = e && e.name === 'AbortError' ? '豆包TTS请求超时' : '豆包TTS请求失败（网络异常）';
                _notifyAudioDiag('doubao_fetch_error', {
                    err: errMsg,
                    reason: String((e && (e.message || e.name)) || e || 'unknown'),
                });
                if (typeof done === 'function') done(false, errMsg);
            }).finally(() => {
                clearTimeout(timer);
            });
        }

        function _playNotifyVoiceByBrowser(contentText = '', done = null) {
            // 已禁用浏览器语音链路，保留函数仅为兼容旧调用。
            if (typeof done === 'function') done(false);
        }

        function _playNotifyVoiceOnce(contentText = '', done = null) {
            if (notifyTtsReady) {
                _playNotifyVoiceByDoubao(contentText, done);
                return;
            }
            if (typeof done === 'function') done(false, '豆包TTS未就绪（notify_tts_ready=false）');
        }

        function processNotifyVoiceQueue() {
            if (notifyVoicePlaying) return;
            if (!notifyVoiceQueue.length) return;

            notifyVoicePlaying = true;
            const item = notifyVoiceQueue.shift();
            const now = Date.now();
            const gapMs = item.force ? 0 : Math.max(0, 1200 - (now - lastNotifyVoiceAt));

            if (notifyVoiceTimer) {
                clearTimeout(notifyVoiceTimer);
                notifyVoiceTimer = null;
            }

            notifyVoiceTimer = setTimeout(() => {
                _playNotifyVoiceOnce(item.contentText, () => {
                    lastNotifyVoiceAt = Date.now();
                    notifyVoicePlaying = false;
                    processNotifyVoiceQueue();
                });
            }, gapMs);
        }

        function announceNewNotifyByVoice(force = false, contentText = '') {
            const cleanText = String(contentText || '').trim();
            notifyVoiceQueue.push({ force: !!force, contentText: cleanText });
            processNotifyVoiceQueue();
        }

        function testNotifyVoice() {
            stopNotifyVoicePlayback();
            notifyVoiceQueue.length = 0;
            notifyVoicePlaying = false;
            _notifyAudioDiag('test_click', {
                ready: !!notifyTtsReady,
                provider: notifyTtsProvider,
                ctx_state: _getNotifyAudioCtxState(),
                unlocked: !!notifyAudioUnlocked,
                gain: clampNotifyAudioGain(notifyAudioGainValue),
            });
            unlockNotifyAudioByGesture().then((unlockOk) => {
                _notifyAudioDiag('test_after_unlock', {
                    unlock_ok: !!unlockOk,
                    ctx_state: _getNotifyAudioCtxState(),
                    unlocked: !!notifyAudioUnlocked,
                    gain: clampNotifyAudioGain(notifyAudioGainValue),
                });
                _playNotifyVoiceOnce('这是一条测试评论内容', (ok, msg) => {
                    _notifyAudioDiag('test_done', {
                        ok: !!ok,
                        msg: String(msg || ''),
                        ctx_state: _getNotifyAudioCtxState(),
                        gain: clampNotifyAudioGain(notifyAudioGainValue),
                    });
                    if (ok) return;
                    alert(`测试失败：${String(msg || '未知错误')}`);
                });
            });
        }

        function switchControlPanel(panelKey, btn) {
            document.querySelectorAll('.control-panel').forEach(panel => panel.classList.remove('active'));
            const targetPanel = document.getElementById(`controlPanel-${panelKey}`);
            if(targetPanel) targetPanel.classList.add('active');

            document.querySelectorAll('.control-tab-btn').forEach(tabBtn => tabBtn.classList.remove('active'));
            if(btn) {
                btn.classList.add('active');
            } else {
                const targetBtn = document.querySelector(`.control-tab-btn[data-panel="${panelKey}"]`);
                if(targetBtn) targetBtn.classList.add('active');
            }
        }

        window.onload = () => {
            bindNotifyTableHeightPersistence();
            restoreNotifyAudioGain();
            bindNotifyAudioGainControl();
            const unlockOnce = () => {
                unlockNotifyAudioByGesture().finally(() => {});
            };
            document.addEventListener('pointerdown', unlockOnce, { once: true });
            switchControlPanel('control');
            fetch('/api/state').then(r=>r.json()).then(d=>{
            document.getElementById('token').value = d.token || '';
            document.getElementById('notifCheckbox').checked = d.notification_monitoring || false;
            document.getElementById('headlessCheckbox').checked = d.headless_mode !== false;
            document.getElementById('delegatedAccount').value = d.delegated_account || '';
            notifyTtsProvider = String(d.notify_tts_provider || 'doubao');
            notifyTtsReady = !!d.notify_tts_ready;
            notifyTtsVoiceType = String(d.notify_tts_voice_type || '');
            applyNotifyTtsState(d);
            setNotifyTtsResult(
                `当前状态: ${notifyTtsReady ? '已就绪' : '未就绪'}\n音色: ${notifyTtsVoiceType || '-'}\n编码: ${d.notify_tts_encoding || '-'}`,
                !notifyTtsReady
            );
            document.getElementById('llmFilterEnabled').checked = !!d.llm_filter_enabled;
            document.getElementById('llmBaseUrl').value = d.llm_filter_base_url || '';
            document.getElementById('llmModel').value = d.llm_filter_model || '';
            document.getElementById('llmApiKey').value = d.llm_filter_api_key || '';
            llmTimeoutMaxSec = Math.max(10, Number(d.llm_filter_timeout_max_sec || 120) || 120);
            document.getElementById('llmTimeoutSec').value = d.llm_filter_timeout_sec || 8;
            document.getElementById('llmIntentPromptTemplate').value = d.llm_intent_prompt_template || '';
            document.getElementById('llmFilterPromptTemplate').value = d.llm_filter_prompt_template || '';
            document.getElementById('dmLlmRewriteEnabled').checked = (d.dm_llm_rewrite_enabled !== false);
            document.getElementById('dmLlmRewritePromptTemplate').value = d.dm_llm_rewrite_prompt_template || '';
            document.getElementById('notifyVoiceBlockKeywords').value = d.notify_voice_block_keywords_text || '';
            refreshNotifyVoiceBlockKeywordsFromInput();
            syncTemplatesFromPayload(d);
            renderTasks(d.tasks);
            if(d.is_running) setStatus(true);

            if(d.pending && d.pending.length > 0) {
                d.pending.forEach(item => addRow(item, false));
            }
            updatesLastSeq = Math.max(0, Number(d.updates_last_seq || 0) || 0);

            refreshFilterOptions('notify');
            refreshFilterOptions('tweet');
            applyResultFilter('notify');
            applyResultFilter('tweet');
            syncNotifyFlowStatus();
            });
        };

        function escapeHtml(str) {
            return String(str || '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }

        function escapeAttr(str) {
            return escapeHtml(str).replace(/`/g, '&#96;');
        }

        function setStatus(run) {
            document.getElementById('startBtn').disabled = run;
            document.getElementById('stopBtn').disabled = !run;
            document.getElementById('token').disabled = run;

            const dot = document.getElementById('statusDot');
            const text = document.getElementById('statusText');

            if(run) {
                dot.classList.add('running');
                text.textContent = '运行中';
                text.style.color = 'var(--success)';
            } else {
                dot.classList.remove('running');
                text.textContent = '已停止';
                text.style.color = 'var(--danger)';
            }
        }

        function renderTasks(t) {
            const div = document.getElementById('taskList');
            if(!t || t.length === 0) {
                div.innerHTML = '<div style="text-align:center; padding:30px; color:var(--text-secondary); font-size:13px;">暂无监控任务</div>';
                return;
            }
            div.innerHTML = t.map(x => `
                <div class="task-item">
                    <div class="task-info">
                        <div class="task-url">${x.url.split('status/')[1] || x.url}</div>
                        <div class="task-time">上次检查: ${x.last_check}</div>
                    </div>
                    <button class="task-delete" onclick="delTask('${x.url}')">✕</button>
                </div>`).join('');
        }

        function addTask() {
            const u = document.getElementById('newUrl').value;
            if(!u) return;
            fetch('/api/task/add', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url:u})})
                .then(r=>r.json()).then(d=>{ renderTasks(d.tasks); document.getElementById('newUrl').value=''; });
        }

        function delTask(u) {
            fetch('/api/task/remove', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url:u})})
                .then(r=>r.json()).then(d=>renderTasks(d.tasks));
        }

        function toggle(s) {
            const t = document.getElementById('token').value;
            if(s && !t) return alert('请先输入 Token');
            fetch(s?'/api/start':'/api/stop', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({token:t})})
                .then(r=>r.json()).then(d => { if(d.status==='ok') setStatus(s); });
        }

        function toggleNotificationMonitoring() {
            const enabled = document.getElementById('notifCheckbox').checked;
            fetch('/api/toggle_notification', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({enabled:enabled})})
                .then(r=>r.json());
        }

        function toggleHeadlessMode() {
            const enabled = document.getElementById('headlessCheckbox').checked;
            fetch('/api/toggle_headless', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({enabled:enabled})})
                .then(r=>r.json()).then(d => {
                    if(d.status === 'ok') {
                        const modeText = enabled ? '无头模式' : '有头模式(调试)';
                        if(d.auto_restarted) {
                            alert(`🖥️ 已切换为${modeText}\n✅ 监控已自动重启`);
                        } else {
                            alert(`🖥️ 已切换为${modeText}`);
                        }
                    } else {
                        alert(`切换失败: ${d.msg || '未知错误'}`);
                    }
                });
        }

        function saveDelegatedAccount() {
            const account = document.getElementById('delegatedAccount').value.trim();
            fetch('/api/set_delegated_account', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({account:account})})
                .then(r=>r.json()).then(d => {
                    if(d.status === 'ok') {
                        alert(account ? `✅ 已设置委派账户: ${account}` : '✅ 已清除委派账户');
                    }
                });
        }

        function setJumpToRepliesResult(text, isError=false) {
            const box = document.getElementById('jumpToRepliesResult');
            if(!box) return;
            box.style.color = isError ? 'var(--danger)' : 'var(--text-secondary)';
            box.textContent = String(text || '');
        }

        function normalizeTwitterHandle(raw) {
            const v = String(raw || '').trim().replace(/^@+/, '').toLowerCase();
            return v.replace(/[^a-z0-9_]/g, '');
        }

        function handleJumpToRepliesEnter(evt) {
            if(!evt || evt.isComposing) return;
            if(evt.key !== 'Enter') return;
            evt.preventDefault();

            const input = document.getElementById('jumpToRepliesHandle');
            if(!input) return;
            const handle = normalizeTwitterHandle(input.value);
            if(!handle) {
                setJumpToRepliesResult('请输入有效的推特 @ID', true);
                return;
            }
            input.value = `@${handle}`;
            setJumpToRepliesResult(`正在打开 @${handle} 的回复页...`, false);

            fetch('/api/open_user_replies_page', {
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body: JSON.stringify({handle})
            }).then(async r => {
                let data = {};
                try { data = await r.json(); } catch(_) {}
                if(!r.ok || data.status !== 'ok') {
                    const msg = String((data && data.msg) || '跳转失败');
                    setJumpToRepliesResult(msg, true);
                    return;
                }
                const opened = String(data.handle || `@${handle}`);
                setJumpToRepliesResult(`已在程序浏览器打开 ${opened} 的回复页`, false);
            }).catch(() => {
                setJumpToRepliesResult('网络异常，跳转失败', true);
            });
        }

        function setNotifyTtsResult(text, isError=false) {
            const box = document.getElementById('notifyTtsResult');
            if(!box) return;
            box.style.color = isError ? 'var(--danger)' : 'var(--text-secondary)';
            box.textContent = String(text || '');
        }

        function collectNotifyTtsPayload() {
            return {
                enabled: !!document.getElementById('notifyTtsEnabled').checked,
                app_id: document.getElementById('notifyTtsAppId').value.trim(),
                access_token: document.getElementById('notifyTtsAccessToken').value.trim(),
                secret_key: document.getElementById('notifyTtsSecretKey').value.trim(),
                voice_type: document.getElementById('notifyTtsVoiceType').value.trim(),
            };
        }

        function applyNotifyTtsState(payload) {
            const d = payload || {};
            const setVal = (id, v) => {
                const el = document.getElementById(id);
                if(!el) return;
                el.value = String(v ?? '');
            };
            const setCheck = (id, v) => {
                const el = document.getElementById(id);
                if(!el) return;
                el.checked = !!v;
            };
            setCheck('notifyTtsEnabled', !!d.notify_tts_enabled);
            setVal('notifyTtsAppId', d.notify_tts_app_id || '');
            setVal('notifyTtsAccessToken', d.notify_tts_access_token || '');
            setVal('notifyTtsSecretKey', d.notify_tts_secret_key || '');
            setVal('notifyTtsVoiceType', d.notify_tts_voice_type || 'zh_female_vv_uranus_bigtts');
        }

        function saveNotifyTtsConfig() {
            const payload = collectNotifyTtsPayload();
            fetch('/api/set_notify_tts_config', {
                method: 'POST',
                headers: {'Content-Type':'application/json'},
                body: JSON.stringify(payload)
            }).then(r => r.json()).then(d => {
                if(d.status !== 'ok') {
                    setNotifyTtsResult(`保存失败: ${d.msg || '未知错误'}`, true);
                    return;
                }
                applyNotifyTtsState(d);
                notifyTtsProvider = String(d.notify_tts_provider || 'doubao');
                notifyTtsReady = !!d.notify_tts_ready;
                notifyTtsVoiceType = String(d.notify_tts_voice_type || '');
                const lines = [
                    `保存成功: ${notifyTtsReady ? '已就绪' : '未就绪'}`,
                    `音色: ${notifyTtsVoiceType || '-'}`,
                    `编码: ${d.notify_tts_encoding || '-'}`,
                ];
                if(d.saved_to_local_file === false) {
                    lines.push(`本地文件落盘失败: ${d.save_error || '-'}`);
                }
                setNotifyTtsResult(lines.join('\n'), false);
            }).catch(() => {
                setNotifyTtsResult('网络异常，保存失败', true);
            });
        }

        function testNotifyTtsConfig() {
            const payload = collectNotifyTtsPayload();
            setNotifyTtsResult('正在测试豆包TTS配置...');
            fetch('/api/notify_tts/test', {
                method: 'POST',
                headers: {'Content-Type':'application/json'},
                body: JSON.stringify({ ...payload, text: '豆包语音配置测试，声音正常。' })
            }).then(r => r.json()).then(d => {
                if(d.status !== 'ok') {
                    setNotifyTtsResult(`测试失败: ${d.msg || '未知错误'}`, true);
                    return;
                }
                const lines = [
                    `测试通过: ${d.msg || 'ok'}`,
                    `延迟: ${d.latency_ms || 0}ms`,
                    `返回音频长度: ${d.audio_b64_len || 0}`,
                    `音色: ${d.notify_tts_voice_type || '-'}`,
                ];
                setNotifyTtsResult(lines.join('\n'), false);
            }).catch(() => {
                setNotifyTtsResult('网络异常，测试失败', true);
            });
        }

        function saveLlmFilterConfig() {
            const enabled = document.getElementById('llmFilterEnabled').checked;
            const baseUrl = document.getElementById('llmBaseUrl').value.trim();
            const model = document.getElementById('llmModel').value.trim();
            const apiKey = document.getElementById('llmApiKey').value.trim() || 'EMPTY';
            const llmIntentPromptTemplate = (document.getElementById('llmIntentPromptTemplate').value || '').trim();
            const llmFilterPromptTemplate = (document.getElementById('llmFilterPromptTemplate').value || '').trim();
            const dmLlmRewriteEnabled = !!document.getElementById('dmLlmRewriteEnabled').checked;
            const dmLlmRewritePromptTemplate = (document.getElementById('dmLlmRewritePromptTemplate').value || '').trim();
            const notifyVoiceBlockKeywordsText = (document.getElementById('notifyVoiceBlockKeywords').value || '').trim();
            let timeoutSec = parseFloat(document.getElementById('llmTimeoutSec').value || '8');
            if(Number.isNaN(timeoutSec)) timeoutSec = 8;
            timeoutSec = Math.max(2, Math.min(llmTimeoutMaxSec, timeoutSec));
            document.getElementById('llmTimeoutSec').value = timeoutSec;
            refreshNotifyVoiceBlockKeywordsFromInput();

            if(enabled && (!baseUrl || !model)) {
                alert('启用 LLM 过滤时，Base URL 和模型名不能为空');
                return;
            }

            fetch('/api/set_llm_filter_config', {
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body:JSON.stringify({
                    enabled: enabled,
                    base_url: baseUrl,
                    model: model,
                    api_key: apiKey,
                    timeout_sec: timeoutSec,
                    llm_intent_prompt_template: llmIntentPromptTemplate,
                    llm_filter_prompt_template: llmFilterPromptTemplate,
                    dm_llm_rewrite_enabled: dmLlmRewriteEnabled,
                    dm_llm_rewrite_prompt_template: dmLlmRewritePromptTemplate,
                    notify_voice_block_keywords_text: notifyVoiceBlockKeywordsText
                })
            }).then(r=>r.json()).then(d => {
                if(d.status === 'ok') {
                    document.getElementById('llmIntentPromptTemplate').value = d.llm_intent_prompt_template || llmIntentPromptTemplate;
                    document.getElementById('llmFilterPromptTemplate').value = d.llm_filter_prompt_template || llmFilterPromptTemplate;
                    document.getElementById('dmLlmRewriteEnabled').checked = (d.dm_llm_rewrite_enabled !== false);
                    document.getElementById('dmLlmRewritePromptTemplate').value = d.dm_llm_rewrite_prompt_template || dmLlmRewritePromptTemplate;
                    document.getElementById('notifyVoiceBlockKeywords').value = d.notify_voice_block_keywords_text || notifyVoiceBlockKeywordsText;
                    refreshNotifyVoiceBlockKeywordsFromInput();
                    alert(`✅ LLM过滤配置已保存${enabled ? '并启用' : '（当前禁用）'}`);
                } else {
                    alert(`保存失败: ${d.msg || '未知错误'}`);
                }
            }).catch(() => {
                alert('网络异常，保存失败');
            });
        }

        function collectLlmRuntimePayload() {
            let timeoutSec = parseFloat(document.getElementById('llmTimeoutSec').value || '8');
            if(Number.isNaN(timeoutSec)) timeoutSec = 8;
            timeoutSec = Math.max(2, Math.min(llmTimeoutMaxSec, timeoutSec));
            document.getElementById('llmTimeoutSec').value = timeoutSec;
            return {
                base_url: document.getElementById('llmBaseUrl').value.trim(),
                model: document.getElementById('llmModel').value.trim(),
                api_key: (document.getElementById('llmApiKey').value || '').trim() || 'EMPTY',
                timeout_sec: timeoutSec
            };
        }

        function isIntentVoiceModeEnabled() {
            const enabledEl = document.getElementById('llmFilterEnabled');
            return !!(enabledEl && enabledEl.checked);
        }

        function resolveNotifyVoiceShouldSpeak(analysis) {
            if(!analysis || typeof analysis !== 'object') return false;
            if(typeof analysis.voice_should_notify === 'boolean') {
                return analysis.voice_should_notify;
            }
            const forceNotify = !!analysis.force_notify;
            if(forceNotify) return true;
            if(!!analysis.block_intent) return false;
            const level = String(analysis.intent_level || '').toLowerCase();
            if(level === 'low' || level === 'noise') return false;
            const score = Number(analysis.intent_score || 0);
            return (!!analysis.is_intent_user) && score >= 55;
        }

        function enqueueNotifyIntentCheck(item) {
            if(!item || item.source !== '通知页面') return;
            notifyIntentQueue.push({
                content: String(item.content || '').trim(),
                analysis: item
            });
            processNotifyIntentQueue();
        }

        function processNotifyIntentQueue() {
            if(notifyIntentBusy) return;
            if(!notifyIntentQueue.length) return;

            const task = notifyIntentQueue.shift();
            const content = String(task.content || '').trim();
            if(!content) {
                processNotifyIntentQueue();
                return;
            }
            if(shouldSuppressNotifyVoice(content)) {
                processNotifyIntentQueue();
                return;
            }

            // 优先复用后端已计算好的意向结果，避免重复调用模型。
            if(task.analysis && typeof task.analysis === 'object') {
                if(resolveNotifyVoiceShouldSpeak(task.analysis)) {
                    announceNewNotifyByVoice(false, content);
                }
                processNotifyIntentQueue();
                return;
            }

            const payload = collectLlmRuntimePayload();
            // 即便未配置LLM，也走后端规则分析兜底，避免漏播报短意向评论

            notifyIntentBusy = true;
            fetch('/api/llm_filter/analyze', {
                method: 'POST',
                headers: {'Content-Type':'application/json'},
                body: JSON.stringify({...payload, content, analyze_source: 'notify_voice_queue'})
            }).then(r => r.json()).then(d => {
                if(d.status !== 'ok') return;
                const a = d.analysis || {};
                if(resolveNotifyVoiceShouldSpeak(a)) {
                    announceNewNotifyByVoice(false, content);
                }
            }).catch(() => {
                // 分析失败时不播报，避免误报
            }).finally(() => {
                notifyIntentBusy = false;
                processNotifyIntentQueue();
            });
        }

        function setLlmIntentResult(text, isError=false) {
            const box = document.getElementById('llmIntentResult');
            if(!box) return;
            box.style.color = isError ? 'var(--danger)' : 'var(--text-secondary)';
            box.textContent = String(text || '');
        }

        function testLlmFilterModel() {
            const payload = collectLlmRuntimePayload();
            if(!payload.base_url || !payload.model) {
                setLlmIntentResult('请先填写 Base URL 和模型名', true);
                return;
            }
            setLlmIntentResult('正在测试模型连通性...');
            fetch('/api/llm_filter/test', {
                method: 'POST',
                headers: {'Content-Type':'application/json'},
                body: JSON.stringify(payload)
            }).then(r => r.json()).then(d => {
                if(d.status === 'ok') {
                    const msg = [
                        `模型可用: ${d.model || '-'}`,
                        `延迟: ${d.latency_ms || 0}ms`,
                        `接口: ${d.endpoint || '-'}`,
                    ].join('\n');
                    setLlmIntentResult(msg, false);
                } else {
                    setLlmIntentResult(`测试失败: ${d.msg || '未知错误'}`, true);
                }
            }).catch(() => {
                setLlmIntentResult('网络异常，模型测试失败', true);
            });
        }

        function analyzeCommentIntentByLlm() {
            const payload = collectLlmRuntimePayload();
            const content = (document.getElementById('llmIntentInput').value || '').trim();
            if(!content) {
                setLlmIntentResult('请输入要分析的评论内容', true);
                return;
            }
            setLlmIntentResult('正在分析评论意向...');
            fetch('/api/llm_filter/analyze', {
                method: 'POST',
                headers: {'Content-Type':'application/json'},
                body: JSON.stringify({...payload, content, analyze_source: 'manual_panel'})
            }).then(r => r.json()).then(d => {
                if(d.status !== 'ok') {
                    setLlmIntentResult(`分析失败: ${d.msg || '未知错误'}`, true);
                    return;
                }
                const a = d.analysis || {};
                const signals = Array.isArray(a.signals) ? a.signals.join(', ') : '';
                const signalsLower = String(signals || '').toLowerCase();
                const reasonRaw = String(a.reason || '').trim();
                const reasonLower = reasonRaw.toLowerCase();
                const llmUsed = Boolean(a.llm_used);
                const llmReason = String(a.llm_reason || '').trim();
                const finalReasonCode = reasonRaw || (llmUsed ? 'rule_llm_blended' : 'rule_only');
                let finalReason = reasonRaw;
                if(!finalReason || reasonLower === 'rule_llm_blended' || reasonLower === 'rule_only' || reasonRaw === '-') {
                    if(
                        signalsLower.includes('emoji_only') ||
                        signalsLower.includes('very_short_text') ||
                        signalsLower.includes('short_text') ||
                        String(a.intent_level || '').toLowerCase() === 'noise' ||
                        String(a.intent_level || '').toLowerCase() === 'low'
                    ) {
                        finalReason = '纯闲聊、纯表情、无意义灌水';
                    } else {
                        finalReason = '未识别到明确购买意向';
                    }
                }
                const lines = [
                    `意向等级: ${a.intent_level || '-'} (${a.intent_score ?? 0}分)`,
                    `是否意向用户: ${a.is_intent_user ? '是' : '否'}`,
                    `是否语音播报: ${a.voice_should_notify ? '是' : '否'}`,
                    `规则分: ${a.rule_score ?? '-'} | LLM分: ${a.llm_score ?? '-'}`,
                    `LLM是否参与: ${llmUsed ? '是' : '否'}`,
                    `识别信号: ${signals || '-'}`,
                    `判定依据(最终): ${finalReasonCode}`,
                    `判定依据(LLM): ${llmReason || '-'}`,
                ];
                if(finalReason && finalReason !== finalReasonCode) {
                    lines.push(`判定解释: ${finalReason}`);
                }
                if(a.llm_error) {
                    lines.push(`LLM异常: ${a.llm_error}`);
                }
                setLlmIntentResult(lines.join('\n'), false);
            }).catch(() => {
                setLlmIntentResult('网络异常，评论分析失败', true);
            });
        }

        function getTemplateArray(type) {
            return type === 'reply' ? notifyReplyTemplates : dmMessageTemplates;
        }

        function getTemplateTypeName(type) {
            return type === 'reply' ? '评论回复' : '私信';
        }

        function getTemplateInput(type) {
            return document.getElementById(type === 'reply' ? 'replyTemplateInput' : 'dmTemplateInput');
        }

        function getTemplateSubmitBtn(type) {
            return document.getElementById(type === 'reply' ? 'replyTemplateSubmitBtn' : 'dmTemplateSubmitBtn');
        }

        function getTemplateCancelBtn(type) {
            return document.getElementById(type === 'reply' ? 'replyTemplateCancelBtn' : 'dmTemplateCancelBtn');
        }

        function applyTemplateEditUi(type) {
            const isEdit = templateEditState[type] >= 0;
            const submitBtn = getTemplateSubmitBtn(type);
            const cancelBtn = getTemplateCancelBtn(type);
            if(submitBtn) {
                submitBtn.textContent = isEdit
                    ? '💾 保存修改'
                    : (type === 'reply' ? '➕ 添加评论文案' : '➕ 添加私信文案');
            }
            if(cancelBtn) {
                cancelBtn.style.display = isEdit ? 'inline-flex' : 'none';
            }
        }

        function startTemplateEdit(type, index, content) {
            templateEditState[type] = index;
            const input = getTemplateInput(type);
            if(input) {
                input.value = content || '';
                input.focus();
                try {
                    if(typeof input.setSelectionRange === 'function') {
                        input.setSelectionRange(input.value.length, input.value.length);
                    }
                } catch (_) {}
            }
            applyTemplateEditUi(type);
        }

        function cancelTemplateEdit(type) {
            templateEditState[type] = -1;
            const input = getTemplateInput(type);
            if(input) input.value = '';
            applyTemplateEditUi(type);
        }

        function syncTemplatesFromPayload(payload) {
            notifyReplyTemplates = Array.isArray(payload.notify_reply_templates) ? payload.notify_reply_templates.slice() : [];
            dmMessageTemplates = Array.isArray(payload.dm_message_templates) ? payload.dm_message_templates.slice() : [];
            if(templateEditState.reply >= notifyReplyTemplates.length) templateEditState.reply = -1;
            if(templateEditState.dm >= dmMessageTemplates.length) templateEditState.dm = -1;
            renderTemplateManager();
        }

        function renderTemplateManager() {
            renderTemplateList('reply', 'replyTemplateList');
            renderTemplateList('dm', 'dmTemplateList');
            applyTemplateEditUi('reply');
            applyTemplateEditUi('dm');
            refreshNotifyTemplateSelects();
        }

        function renderTemplateList(type, listId) {
            const list = document.getElementById(listId);
            const templates = getTemplateArray(type);
            if(!list) return;
            if(!templates.length) {
                list.innerHTML = '<li><div class="template-text" style="color:var(--text-secondary);">暂无模板</div></li>';
                return;
            }
            list.innerHTML = templates.map((tpl, idx) => `
                <li>
                    <div class="template-text">${escapeHtml(tpl)}</div>
                    <div class="template-actions">
                        <button class="btn-ghost btn-sm" onclick="editTemplate('${type}', ${idx})">✏️ 修改</button>
                        <button class="btn-danger btn-sm" onclick="deleteTemplate('${type}', ${idx})">🗑️ 删除</button>
                    </div>
                </li>
            `).join('');
        }

        function handleTemplateApiResponse(d, failPrefix) {
            if(!d || d.status !== 'ok') {
                alert(`${failPrefix}: ${(d && d.msg) ? d.msg : '未知错误'}`);
                return false;
            }
            syncTemplatesFromPayload(d);
            return true;
        }

        function submitTemplate(type) {
            const input = getTemplateInput(type);
            if(!input) return;
            const content = (input.value || '').trim();
            if(!content) {
                alert(`请输入${getTemplateTypeName(type)}文案`);
                return;
            }

            const editingIndex = templateEditState[type];
            if(editingIndex >= 0) {
                fetch('/api/template/update', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({type, index: editingIndex, content})
                }).then(r => r.json()).then(d => {
                    if(handleTemplateApiResponse(d, '修改模板失败')) {
                        cancelTemplateEdit(type);
                    }
                }).catch(() => {
                    alert('网络异常，修改模板失败');
                });
                return;
            }

            fetch('/api/template/add', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({type, content})
            }).then(r => r.json()).then(d => {
                if(handleTemplateApiResponse(d, '添加模板失败')) {
                    input.value = '';
                    applyTemplateEditUi(type);
                }
            }).catch(() => {
                alert('网络异常，添加模板失败');
            });
        }

        function editTemplate(type, index) {
            const templates = getTemplateArray(type);
            if(index < 0 || index >= templates.length) return;
            startTemplateEdit(type, index, templates[index]);
        }

        function deleteTemplate(type, index) {
            const templates = getTemplateArray(type);
            if(index < 0 || index >= templates.length) return;
            if(!confirm(`确定删除这条${getTemplateTypeName(type)}文案吗？`)) return;
            fetch('/api/template/delete', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({type, index})
            }).then(r => r.json()).then(d => {
                if(handleTemplateApiResponse(d, '删除模板失败')) {
                    cancelTemplateEdit(type);
                }
            }).catch(() => {
                alert('网络异常，删除模板失败');
            });
        }

        function buildTemplateOptionHtml(templates) {
            return templates.map(t => {
                const optionValue = escapeAttr(t);
                const optionText = escapeHtml(String(t).replace(/\s+/g, ' ').trim());
                return `<option value="${optionValue}">${optionText}</option>`;
            }).join('');
        }

        function updateSelectOptions(select, templates, placeholderText) {
            if(!select) return;
            const selectedValue = select.value || '';
            const optionsHtml = buildTemplateOptionHtml(templates);
            select.innerHTML = `<option value="">${escapeHtml(placeholderText)}</option>${optionsHtml}`;
            if(selectedValue && templates.includes(selectedValue)) {
                select.value = selectedValue;
            }
        }

        function refreshNotifyTemplateSelects() {
            const rows = getTableRows('notify');
            rows.forEach(row => {
                updateSelectOptions(row.querySelector('.reply-template-select'), notifyReplyTemplates, '选择回复内容...');
                updateSelectOptions(row.querySelector('.dm-template-select'), dmMessageTemplates, '选择私信内容...');
            });
        }

        function markDone(key, btn) {
            const row = btn.closest('tr');
            const handle = row ? (row.getAttribute('data-handle') || '') : '';
            if(row) row.style.opacity = '0.3';

            fetch('/api/mark_done', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({key:key, handle:handle})})
                .then(r=>r.json()).then(d => {
                    if(d.status === 'ok') {
                        setTimeout(() => {
                            if(row) row.remove();
                            refreshFilterOptions('notify');
                            refreshFilterOptions('tweet');
                            updateResultCount();
                        }, 300);
                    }
                });
        }

        let suppressExternalLinkUntil = 0;

        function markActionClick(evt) {
            if(evt) {
                evt.preventDefault();
                evt.stopPropagation();
            }
            suppressExternalLinkUntil = Date.now() + 1200;
        }

        function handleUserLinkClick(evt) {
            if(Date.now() < suppressExternalLinkUntil) {
                if(evt) {
                    evt.preventDefault();
                    evt.stopPropagation();
                }
                return false;
            }
            return true;
        }

        function markDoneFromButton(evt, btn) {
            markActionClick(evt);
            const row = btn.closest('tr');
            const key = row ? (row.getAttribute('data-key') || '') : '';
            if(!key) return;
            markDone(key, btn);
        }

        function isNotifyItemReplied(item) {
            return !!(item && (item.notify_replied || item.reply_checked));
        }

        const notifyFlowStageLabels = {
            reply_pending: '等待回复',
            match_card: '定位评论',
            share_link_ready: '链接就绪',
            reply_sent: '首评已发',
            dm_opening: '打开私信',
            dm_link_sent: '私信链接已发',
            dm_text_generating: '生成私信文案',
            dm_text_sent: '私信文案已发',
            dm_closed_confirmed: '私信关闭已确认',
            retry_waiting: '等待重试',
            done: '流程完成'
        };

        function resolveNotifyFlowLabel(stage) {
            const key = String(stage || '').trim().toLowerCase();
            return notifyFlowStageLabels[key] || (key || '未开始');
        }

        function applyNotifyFlowState(row, data) {
            if(!row || !data) return;
            const stage = String(data.flow_stage || data.notify_flow_stage || row.getAttribute('data-flow-stage') || '').trim();
            const errorCode = String(data.flow_error_code || data.notify_flow_error_code || '').trim();
            const errorDetail = String(data.flow_error_detail || data.notify_flow_error_detail || data.notify_flow_error || '').trim();
            const retryTime = String(data.retry_time || data.notify_retry_time || '').trim();
            const attemptRaw = data.attempt ?? data.notify_flow_attempt ?? '';
            const attemptText = String(attemptRaw || '').trim();

            row.setAttribute('data-flow-stage', stage);
            row.setAttribute('data-flow-error-code', errorCode);
            row.setAttribute('data-flow-error-detail', errorDetail);
            row.setAttribute('data-flow-retry-time', retryTime);
            row.setAttribute('data-flow-attempt', attemptText);

            const stageEl = row.querySelector('.flow-stage');
            const errorEl = row.querySelector('.flow-error');
            const retryEl = row.querySelector('.flow-retry');
            const retryBtn = row.querySelector('.btn-retry');

            if(stageEl) {
                const attemptSuffix = attemptText ? ` | 尝试${attemptText}` : '';
                stageEl.textContent = `阶段: ${resolveNotifyFlowLabel(stage)}${attemptSuffix}`;
            }
            if(errorEl) {
                if(errorCode || errorDetail) {
                    errorEl.textContent = `错误: ${errorCode || '-'} ${errorDetail || ''}`.trim();
                    errorEl.style.display = '';
                } else {
                    errorEl.textContent = '';
                    errorEl.style.display = 'none';
                }
            }
            if(retryEl) {
                if(retryTime) {
                    retryEl.textContent = `下次重试: ${retryTime}`;
                    retryEl.style.display = '';
                } else {
                    retryEl.textContent = '';
                    retryEl.style.display = 'none';
                }
            }
            if(retryBtn) {
                retryBtn.style.display = (stage === 'retry_waiting') ? '' : 'none';
            }
        }

        function applyNotifyReplyState(row, replied, replyTime='') {
            if(!row) return;
            row.setAttribute('data-notify-replied', replied ? '1' : '0');

            const replyBtn = row.querySelector('.btn-reply');
            const replyState = row.querySelector('.reply-state');
            const replySelect = row.querySelector('.reply-template-select');
            const dmSelect = row.querySelector('.dm-template-select');

            if(replyBtn) {
                replyBtn.disabled = false;
                replyBtn.textContent = replied ? '↩ 再次回复' : '↩ 回复';
                replyBtn.classList.remove('done');
            }
            if(replySelect) replySelect.disabled = false;
            if(dmSelect) dmSelect.disabled = false;

            if(replyState) {
                if(replied) {
                    const suffix = replyTime ? ` (${replyTime})` : '';
                    replyState.textContent = `已回复${suffix}`;
                    replyState.classList.add('done');
                } else {
                    replyState.textContent = '未回复';
                    replyState.classList.remove('done');
                }
            }
        }

        function sendNotifyReply(evt, btn) {
            markActionClick(evt);
            const row = btn.closest('tr');
            const key = row ? (row.getAttribute('data-key') || '') : '';
            const handle = row ? (row.getAttribute('data-handle') || '') : '';
            const replySelect = row ? row.querySelector('.reply-template-select') : null;
            const dmSelect = row ? row.querySelector('.dm-template-select') : null;
            const message = replySelect ? (replySelect.value || '').trim() : '';
            const dmMessage = dmSelect ? (dmSelect.value || '').trim() : '';
            if(!key || !message) {
                alert('请先选择回复内容');
                return;
            }
            if(!dmMessage) {
                alert('请先选择私信内容');
                return;
            }

            btn.disabled = true;
            const oldText = btn.textContent;
            btn.textContent = '发送中...';

            fetch('/api/notify_reply', {
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body:JSON.stringify({key:key, message:message, dm_message:dmMessage})
            }).then(r=>r.json()).then(d => {
                if(d.status === 'ok') {
                    const replyTime = (d.reply_time || '').trim();
                    applyNotifyReplyState(row, true, replyTime);
                    applyNotifyFlowState(row, {
                        flow_stage: d.flow_stage || 'done',
                        attempt: d.attempt || '',
                        retry_time: d.retry_time || '',
                        flow_error_code: '',
                        flow_error_detail: ''
                    });
                    alert(`✅ 已回复 ${handle || ''}`);
                } else if(d.status === 'retry_waiting') {
                    applyNotifyReplyState(row, false, '');
                    applyNotifyFlowState(row, {
                        flow_stage: d.flow_stage || 'retry_waiting',
                        attempt: d.attempt || '',
                        retry_time: d.retry_time || '',
                        flow_error_code: d.flow_error_code || '',
                        flow_error_detail: d.flow_error_detail || d.msg || ''
                    });
                    alert(`⚠ 已加入重试队列: ${d.msg || '稍后自动重试'}`);
                } else {
                    applyNotifyFlowState(row, {
                        flow_stage: d.flow_stage || row.getAttribute('data-flow-stage') || '',
                        attempt: d.attempt || '',
                        retry_time: d.retry_time || '',
                        flow_error_code: d.flow_error_code || '',
                        flow_error_detail: d.msg || ''
                    });
                    alert(`回复失败: ${d.msg || '未知错误'}`);
                }
            }).catch(() => {
                alert('网络异常，回复失败');
            }).finally(() => {
                btn.disabled = false;
                const repliedNow = row ? (row.getAttribute('data-notify-replied') === '1') : false;
                btn.textContent = repliedNow ? '↩ 再次回复' : oldText;
            });
        }

        function retryNotifyReply(evt, btn) {
            markActionClick(evt);
            const row = btn.closest('tr');
            const key = row ? (row.getAttribute('data-key') || '') : '';
            if(!key) return;

            const oldText = btn.textContent;
            btn.disabled = true;
            btn.textContent = '重试中...';

            fetch('/api/notify_retry', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({key})
            }).then(r => r.json()).then(d => {
                if(d.status === 'ok') {
                    applyNotifyReplyState(row, true, d.reply_time || '');
                    applyNotifyFlowState(row, {
                        flow_stage: d.flow_stage || 'done',
                        attempt: d.attempt || '',
                        retry_time: '',
                        flow_error_code: '',
                        flow_error_detail: ''
                    });
                    alert('✅ 重试成功');
                    return;
                }
                if(d.status === 'retry_waiting') {
                    applyNotifyFlowState(row, {
                        flow_stage: d.flow_stage || 'retry_waiting',
                        attempt: d.attempt || '',
                        retry_time: d.retry_time || '',
                        flow_error_code: d.flow_error_code || '',
                        flow_error_detail: d.flow_error_detail || d.msg || ''
                    });
                    alert(`⚠ 仍在重试队列: ${d.msg || '稍后自动重试'}`);
                    return;
                }
                applyNotifyFlowState(row, {
                    flow_stage: d.flow_stage || row.getAttribute('data-flow-stage') || '',
                    attempt: d.attempt || '',
                    retry_time: d.retry_time || '',
                    flow_error_code: d.flow_error_code || '',
                    flow_error_detail: d.msg || ''
                });
                alert(`重试失败: ${d.msg || '未知错误'}`);
            }).catch(() => {
                alert('网络异常，重试失败');
            }).finally(() => {
                btn.disabled = false;
                btn.textContent = oldText;
            });
        }

        function clearResults(type) {
            const typeText = type === 'notify' ? '通知' : '推文';
            if(!confirm(`确定要清空所有${typeText}捕获结果吗？`)) return;
            fetch('/api/clear_results', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({type: type})})
                .then(r=>r.json()).then(d => {
                    if(d.status === 'ok') {
                        if(type === 'notify') {
                            document.getElementById('notifyTableBody').innerHTML = '';
                        } else {
                            document.getElementById('tweetTableBody').innerHTML = '';
                        }
                        refreshFilterOptions(type);
                        applyResultFilter(type);
                    }
                });
        }

        function clearBlocklist() {
            if(!confirm('确定要清空黑名单吗？')) return;
            fetch('/api/clear_blocklist', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({})})
                .then(r=>r.json()).then(d => {
                    if(d.status === 'ok') {
                        alert('✅ 已清空黑名单');
                    }
                });
        }

        function getTableRows(type) {
            return Array.from(document.getElementById(tableBodyIds[type]).children);
        }

        function refreshFilterOptions(type) {
            const datalist = document.getElementById(filterOptionIds[type]);
            const input = document.getElementById(filterInputIds[type]);
            if(!datalist || !input) return;

            const values = new Set();
            getTableRows(type).forEach(row => {
                const handle = (row.getAttribute('data-handle') || '').trim();
                if(handle) values.add(handle);
            });
            if(input.value.trim()) values.add(input.value.trim());

            datalist.innerHTML = '';
            Array.from(values).sort((a, b) => a.localeCompare(b, 'zh-Hans-CN')).forEach(value => {
                const option = document.createElement('option');
                option.value = value;
                datalist.appendChild(option);
            });
        }

        function applyResultFilter(type) {
            const input = document.getElementById(filterInputIds[type]);
            if(!input) return;

            const query = input.value.trim().toLowerCase();
            getTableRows(type).forEach(row => {
                const handle = (row.getAttribute('data-handle') || '').toLowerCase();
                const content = (row.querySelector('.content-cell')?.textContent || '').toLowerCase();
                const matched = !query || handle.includes(query) || content.includes(query);
                row.style.display = matched ? '' : 'none';
            });
            updateResultCount();
        }

        function updateResultCount() {
            const notifyRows = getTableRows('notify');
            const tweetRows = getTableRows('tweet');
            const notifyVisibleCount = notifyRows.filter(row => row.style.display !== 'none').length;
            const tweetVisibleCount = tweetRows.filter(row => row.style.display !== 'none').length;
            const notifyFilterActive = document.getElementById(filterInputIds.notify).value.trim() !== '';
            const tweetFilterActive = document.getElementById(filterInputIds.tweet).value.trim() !== '';

            document.getElementById('notifyCount').textContent = notifyFilterActive ? `${notifyVisibleCount}/${notifyRows.length}` : `${notifyRows.length}`;
            document.getElementById('tweetCount').textContent = tweetFilterActive ? `${tweetVisibleCount}/${tweetRows.length}` : `${tweetRows.length}`;
            document.getElementById('notifyEmptyState').style.display = notifyVisibleCount > 0 ? 'none' : 'block';
            document.getElementById('tweetEmptyState').style.display = tweetVisibleCount > 0 ? 'none' : 'block';
        }

        function parseTimeCellToSec(text) {
            const m = String(text || '').trim().match(/^(\d{1,2}):(\d{1,2}):(\d{1,2})$/);
            if(!m) return -1;
            const hh = Number(m[1] || 0);
            const mm = Number(m[2] || 0);
            const ss = Number(m[3] || 0);
            return hh * 3600 + mm * 60 + ss;
        }

        function sortNotifyRowsByLatest() {
            const tbody = document.getElementById('notifyTableBody');
            if(!tbody) return;
            const rows = Array.from(tbody.children);
            if(rows.length <= 1) return;
            rows.sort((a, b) => {
                const ta = parseTimeCellToSec(a.children?.[0]?.textContent || '');
                const tb = parseTimeCellToSec(b.children?.[0]?.textContent || '');
                if(tb !== ta) return tb - ta;
                const sa = Number(a.getAttribute('data-seq') || 0);
                const sb = Number(b.getAttribute('data-seq') || 0);
                return sb - sa;
            });
            rows.forEach(row => tbody.appendChild(row));
        }

        function addRow(i, animate=true) {
            if(document.querySelector(`tr[data-key="${i.key}"]`)) return false;

            const tr = document.createElement('tr');
            if(animate) tr.className = 'row-enter';
            tr.setAttribute('data-handle', i.handle);
            tr.setAttribute('data-key', i.key);

            const isNotify = i.source === '通知页面';
            const isReplied = isNotifyItemReplied(i);
            const safeHandle = escapeHtml(i.handle || '');
            const handlePath = escapeAttr((i.handle || '').replace('@', ''));
            const userCellHtml = isNotify
                ? `<div class="user-info-cell">
                        <a class="user-link" href="https://x.com/${handlePath}/with_replies" target="_blank" onclick="return handleUserLinkClick(event)">${safeHandle}</a>
                   </div>`
                : `<a class="user-link" href="https://x.com/${handlePath}/with_replies" target="_blank" onclick="return handleUserLinkClick(event)">${safeHandle}</a>`;
            const replyOptions = buildTemplateOptionHtml(notifyReplyTemplates);
            const dmOptions = buildTemplateOptionHtml(dmMessageTemplates);
            const replyTime = escapeHtml(i.notify_reply_time || i.reply_time || '');
            const replyStateText = isReplied ? `已回复${replyTime ? ` (${replyTime})` : ''}` : '未回复';
            const replyStateClass = isReplied ? 'reply-state done' : 'reply-state';
            const flowStage = escapeHtml(i.notify_flow_stage || '');
            const flowErrorCode = escapeHtml(i.notify_flow_error_code || '');
            const flowErrorDetail = escapeHtml(i.notify_flow_error_detail || i.notify_flow_error || '');
            const flowRetryTime = escapeHtml(i.notify_retry_time || '');
            const flowAttempt = escapeHtml(i.notify_flow_attempt || '');
            const actionHtml = isNotify
                ? `<div class="action-stack">
                        <div class="${replyStateClass}">${replyStateText}</div>
                        <div class="flow-meta">
                            <div class="flow-stage"></div>
                            <div class="flow-error"></div>
                            <div class="flow-retry"></div>
                        </div>
                        <select class="reply-template-select">
                            <option value="">选择回复内容...</option>
                            ${replyOptions}
                        </select>
                        <select class="dm-template-select">
                            <option value="">选择私信内容...</option>
                            ${dmOptions}
                        </select>
                        <div class="action-btn-row">
                            <button type="button" class="btn-reply btn-sm" onclick="sendNotifyReply(event, this)">${isReplied ? '↩ 再次回复' : '↩ 回复'}</button>
                            <button type="button" class="btn-ghost btn-sm btn-retry" onclick="retryNotifyReply(event, this)" style="display:none;">🔁 重试</button>
                            <button type="button" class="btn-primary btn-sm" onclick="markDoneFromButton(event, this)">✅ 已处理</button>
                        </div>
                   </div>`
                : `<button type="button" class="btn-primary btn-sm" onclick="markDoneFromButton(event, this)">✅ 已处理</button>`;

            tr.innerHTML = `
                <td style="color:var(--text-secondary)">${escapeHtml(i.time || '')}</td>
                <td>${userCellHtml}</td>
                <td class="content-cell">${escapeHtml(i.content || '')}</td>
                <td>${actionHtml}</td>
            `;

            if(isNotify) {
                tr.setAttribute('data-seq', String(++notifyRowSeq));
                document.getElementById('notifyTableBody').prepend(tr);
                const replySelect = tr.querySelector('.reply-template-select');
                const dmSelect = tr.querySelector('.dm-template-select');
                const savedReplyText = (i.notify_reply_text || i.reply_text || '').trim();
                const savedDmText = (i.notify_dm_text || '').trim();
                if(replySelect && savedReplyText) replySelect.value = savedReplyText;
                if(dmSelect && savedDmText) dmSelect.value = savedDmText;
                applyNotifyReplyState(tr, isReplied, i.notify_reply_time || i.reply_time || '');
                applyNotifyFlowState(tr, {
                    flow_stage: flowStage,
                    flow_error_code: flowErrorCode,
                    flow_error_detail: flowErrorDetail,
                    retry_time: flowRetryTime,
                    attempt: flowAttempt
                });
                sortNotifyRowsByLatest();
            } else {
                document.getElementById('tweetTableBody').prepend(tr);
            }
            const type = isNotify ? 'notify' : 'tweet';
            refreshFilterOptions(type);
            applyResultFilter(type);
            return true;
        }

        function syncNotifyFlowStatus() {
            fetch('/api/notify_replies?limit=2000').then(r => r.json()).then(d => {
                if(!d || d.status !== 'ok' || !Array.isArray(d.items)) return;
                d.items.forEach(item => {
                    if(!item || !item.key) return;
                    let row = document.querySelector(`tr[data-key="${item.key}"]`);
                    if(!row) {
                        addRow(item, false);
                        row = document.querySelector(`tr[data-key="${item.key}"]`);
                    }
                    if(!row) return;
                    applyNotifyReplyState(row, isNotifyItemReplied(item), item.notify_reply_time || item.reply_time || '');
                    applyNotifyFlowState(row, item);
                });
            }).catch(() => {});
        }

        function pollUpdatesIncremental() {
            fetch(`/api/updates?since_seq=${encodeURIComponent(String(updatesLastSeq || 0))}`)
                .then(r => r.json())
                .then(d => {
                    if(!d || !Array.isArray(d.new_items)) return;
                    d.new_items.forEach(i => {
                        addRow(i, true);
                        if(i && i.source === '通知页面') {
                            enqueueNotifyIntentCheck(i);
                        }
                    });
                    if(d.tasks) renderTasks(d.tasks);
                    const lastSeq = Number(d.last_seq || 0);
                    if(Number.isFinite(lastSeq) && lastSeq > 0) {
                        updatesLastSeq = Math.max(updatesLastSeq, lastSeq);
                    }
                    if(d.dropped === true) {
                        syncNotifyFlowStatus();
                    }
                    updatesPollFailStreak = 0;
                })
                .catch(() => {
                    updatesPollFailStreak += 1;
                    if(updatesPollFailStreak >= 3) {
                        const now = Date.now();
                        if(now >= updatesRecoverCoolUntil) {
                            updatesRecoverCoolUntil = now + 15000;
                            syncNotifyFlowStatus();
                        }
                    }
                });
        }

        pollUpdatesIncremental();
        setInterval(pollUpdatesIncremental, 1000);
        setInterval(syncNotifyFlowStatus, 6000);
    
