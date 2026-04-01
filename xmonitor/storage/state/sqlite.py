import json
import os
import sqlite3
import time


APP_STATE_KEY = 'app_state'
PROCESSED_USERS_KEY = 'processed_users'


def sqlite_state_file(deps):
    return str(getattr(deps, 'SQLITE_STATE_FILE', os.path.join(deps.DATA_DIR, 'xmonitor_state.sqlite3')))


def sqlite_json_fallback_enabled(deps):
    return bool(getattr(deps, 'STATE_JSON_FALLBACK', True))


def _connect(deps):
    db_path = sqlite_state_file(deps)
    conn = sqlite3.connect(db_path, timeout=5.0)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA synchronous=NORMAL')
    conn.execute(
        'CREATE TABLE IF NOT EXISTS state_kv ('
        'key TEXT PRIMARY KEY, '
        'value_json TEXT NOT NULL, '
        'updated_at REAL NOT NULL'
        ')'
    )
    conn.execute(
        'CREATE TABLE IF NOT EXISTS pending_results ('
        'row_id TEXT PRIMARY KEY, '
        'sort_order INTEGER NOT NULL, '
        'item_json TEXT NOT NULL'
        ')'
    )
    conn.execute(
        'CREATE TABLE IF NOT EXISTS history_ids ('
        'history_id TEXT PRIMARY KEY'
        ')'
    )
    conn.execute(
        'CREATE TABLE IF NOT EXISTS content_dedupe ('
        'signature TEXT PRIMARY KEY, '
        'last_seen_ts REAL NOT NULL'
        ')'
    )
    conn.execute(
        'CREATE TABLE IF NOT EXISTS processed_users_items ('
        'user_value TEXT PRIMARY KEY'
        ')'
    )
    return conn


def save_blob(deps, key, value):
    payload = json.dumps(value, ensure_ascii=False)
    conn = _connect(deps)
    try:
        conn.execute(
            'INSERT INTO state_kv(key, value_json, updated_at) VALUES (?, ?, ?) '
            'ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at',
            (str(key), payload, float(time.time())),
        )
        conn.commit()
    finally:
        conn.close()


def load_blob(deps, key, default=None):
    db_path = sqlite_state_file(deps)
    if not os.path.exists(db_path):
        return default
    conn = _connect(deps)
    try:
        row = conn.execute('SELECT value_json FROM state_kv WHERE key = ?', (str(key),)).fetchone()
    finally:
        conn.close()
    if not row:
        return default
    try:
        return json.loads(row[0])
    except Exception:
        return default


def has_blob(deps, key):
    db_path = sqlite_state_file(deps)
    if not os.path.exists(db_path):
        return False
    conn = _connect(deps)
    try:
        row = conn.execute('SELECT 1 FROM state_kv WHERE key = ? LIMIT 1', (str(key),)).fetchone()
    finally:
        conn.close()
    return bool(row)


def _build_pending_rows(pending_results):
    rows = []
    used = set()
    for idx, item in enumerate(list(pending_results or [])):
        if isinstance(item, dict):
            base = str(item.get('key') or '').strip() or f'idx_{idx}'
            payload = dict(item)
        else:
            base = f'idx_{idx}'
            payload = item
        row_id = base
        suffix = 1
        while row_id in used:
            row_id = f'{base}__{suffix}'
            suffix += 1
        used.add(row_id)
        rows.append((row_id, int(idx), json.dumps(payload, ensure_ascii=False)))
    return rows


def save_structured_state(deps, pending_results, history_ids, content_dedupe):
    pending_rows = _build_pending_rows(pending_results)
    history_rows = [(str(x),) for x in sorted(str(x) for x in set(history_ids or [])) if str(x)]
    dedupe_rows = []
    for sig, ts in dict(content_dedupe or {}).items():
        try:
            dedupe_rows.append((str(sig), float(ts)))
        except Exception:
            continue

    conn = _connect(deps)
    try:
        conn.execute('DELETE FROM pending_results')
        conn.execute('DELETE FROM history_ids')
        conn.execute('DELETE FROM content_dedupe')
        if pending_rows:
            conn.executemany(
                'INSERT INTO pending_results(row_id, sort_order, item_json) VALUES (?, ?, ?)',
                pending_rows,
            )
        if history_rows:
            conn.executemany('INSERT INTO history_ids(history_id) VALUES (?)', history_rows)
        if dedupe_rows:
            conn.executemany(
                'INSERT INTO content_dedupe(signature, last_seen_ts) VALUES (?, ?)',
                dedupe_rows,
            )
        conn.commit()
    finally:
        conn.close()


def load_structured_state(deps):
    db_path = sqlite_state_file(deps)
    if not os.path.exists(db_path):
        return None
    conn = _connect(deps)
    try:
        pending_rows = conn.execute(
            'SELECT row_id, item_json FROM pending_results ORDER BY sort_order ASC, row_id ASC'
        ).fetchall()
        history_rows = conn.execute('SELECT history_id FROM history_ids ORDER BY history_id ASC').fetchall()
        dedupe_rows = conn.execute('SELECT signature, last_seen_ts FROM content_dedupe').fetchall()
    finally:
        conn.close()

    if not pending_rows and not history_rows and not dedupe_rows:
        return None

    pending_results = []
    for _, item_json in pending_rows:
        try:
            pending_results.append(json.loads(item_json))
        except Exception:
            continue
    history_ids = [str(row[0]) for row in history_rows if row and str(row[0])]
    content_dedupe = {}
    for signature, last_seen_ts in dedupe_rows:
        try:
            content_dedupe[str(signature)] = float(last_seen_ts)
        except Exception:
            continue
    return {
        'pending_results': pending_results,
        'history_ids': history_ids,
        'content_dedupe': content_dedupe,
    }


def has_structured_state(deps):
    db_path = sqlite_state_file(deps)
    if not os.path.exists(db_path):
        return False
    conn = _connect(deps)
    try:
        for table in ('pending_results', 'history_ids', 'content_dedupe'):
            row = conn.execute(f'SELECT 1 FROM {table} LIMIT 1').fetchone()
            if row:
                return True
    finally:
        conn.close()
    return False


def save_processed_users_set(deps, processed_users):
    rows = [(str(x),) for x in sorted(str(x) for x in set(processed_users or [])) if str(x)]
    conn = _connect(deps)
    try:
        conn.execute('DELETE FROM processed_users_items')
        if rows:
            conn.executemany('INSERT INTO processed_users_items(user_value) VALUES (?)', rows)
        conn.commit()
    finally:
        conn.close()


def load_processed_users_set(deps):
    db_path = sqlite_state_file(deps)
    if not os.path.exists(db_path):
        return None
    conn = _connect(deps)
    try:
        rows = conn.execute('SELECT user_value FROM processed_users_items ORDER BY user_value ASC').fetchall()
    finally:
        conn.close()
    if not rows:
        return None
    return [str(row[0]) for row in rows if row and str(row[0])]


def has_processed_users_table(deps):
    db_path = sqlite_state_file(deps)
    if not os.path.exists(db_path):
        return False
    conn = _connect(deps)
    try:
        row = conn.execute('SELECT 1 FROM processed_users_items LIMIT 1').fetchone()
    finally:
        conn.close()
    return bool(row)
