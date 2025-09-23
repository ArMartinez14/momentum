# offline_storage.py
import json
import time
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st
from streamlit_local_storage import LocalStorage

_local = LocalStorage()

# ========= Claves =========
KEY_EMAIL             = "mp_email_cached_v1"
KEY_ROLE              = "mp_role_cached_v1"
KEY_WEEK_CACHE_PREFIX = "mp_weekcache_"            # + normalized_email + "_" + monday_date
KEY_MUTATION_QUEUE    = "mp_mutation_queue_v1"
KEY_LAST_SYNC_OK      = "mp_last_sync_ok_v1"
KEY_OFFLINE_FLAG      = "mp_is_offline_v1"

# ========= Generador de keys únicos por llamada =========
def _next_uid(prefix: str, item_key: str) -> str:
    c = st.session_state.get("_ls_uid_counter", 0) + 1
    st.session_state["_ls_uid_counter"] = c
    return f"{prefix}::{item_key}::{c}::{int(time.time()*1000)}"

# ========= Wrappers con key único =========
def _ls_get_raw(item_key: str) -> Optional[str]:
    return _local.getItem(item_key, key=_next_uid("get", item_key))

def _ls_set_raw(item_key: str, value: str) -> None:
    _local.setItem(item_key, value, key=_next_uid("set", item_key))

def _ls_remove(item_key: str) -> None:
    _local.removeItem(item_key, key=_next_uid("rm", item_key))

def _load_json(item_key: str, default: Any):
    try:
        raw = _ls_get_raw(item_key)
        if not raw:
            return default
        return json.loads(raw)
    except Exception:
        return default

def _save_json(item_key: str, value: Any):
    try:
        _ls_set_raw(item_key, json.dumps(value, ensure_ascii=False))
    except Exception:
        pass

# ========= Estado conexión =========
def set_offline_flag(is_offline: bool):
    _ls_set_raw(KEY_OFFLINE_FLAG, "1" if is_offline else "0")

def is_offline() -> bool:
    return (_ls_get_raw(KEY_OFFLINE_FLAG) or "0") == "1"

# ========= Cacheo login =========
def cache_login(email: str, role: str):
    _ls_set_raw(KEY_EMAIL, email or "")
    _ls_set_raw(KEY_ROLE,  role or "")

def get_cached_login() -> Tuple[Optional[str], Optional[str]]:
    return _ls_get_raw(KEY_EMAIL), _ls_get_raw(KEY_ROLE)

def clear_cached_login():
    _ls_remove(KEY_EMAIL)
    _ls_remove(KEY_ROLE)

# ========= Cacheo semana =========
def week_cache_key(normalized_email: str, monday_str: str) -> str:
    return f"{KEY_WEEK_CACHE_PREFIX}{normalized_email}_{monday_str}"

def get_cached_week(normalized_email: str, monday_str: str) -> Optional[Dict[str, Any]]:
    return _load_json(week_cache_key(normalized_email, monday_str), None)

def set_cached_week(normalized_email: str, monday_str: str, week_data: Dict[str, Any]):
    _save_json(week_cache_key(normalized_email, monday_str), week_data)

# ========= Cola de mutaciones =========
# { "id": "...", "ts": 1712345678901, "op": "update_doc", "doc_path": "col/doc", "data": {...}, "merge": true }
def enqueue_mutation(mutation: Dict[str, Any]):
    queue: List[Dict[str, Any]] = _load_json(KEY_MUTATION_QUEUE, [])
    queue.append(mutation)
    _save_json(KEY_MUTATION_QUEUE, queue)

def peek_mutations() -> List[Dict[str, Any]]:
    return _load_json(KEY_MUTATION_QUEUE, [])

def replace_mutations(new_queue: List[Dict[str, Any]]):
    _save_json(KEY_MUTATION_QUEUE, new_queue)

def set_last_sync_ok():
    _ls_set_raw(KEY_LAST_SYNC_OK, str(int(time.time())))

def get_last_sync_ok() -> Optional[int]:
    raw = _ls_get_raw(KEY_LAST_SYNC_OK)
    try:
        return int(raw) if raw else None
    except:
        return None
