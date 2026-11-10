"""Persistent pairing secret; invalid storage never silently invalidates phones."""
import json
import os
from pathlib import Path
import re
import secrets
import tempfile


def _validate(token):
    if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', token):
        raise ValueError('配对凭证损坏，请关闭接收器后使用 --reset-pairing 重置配对。')
    return token


def save_token(path, token):
    token = _validate(token)
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix='.pairing-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump({'version': 1, 'token': token}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_token(path):
    path = Path(path)
    try:
        stored = json.loads(path.read_text(encoding='utf-8'))
        return _validate(stored.get('token') if isinstance(stored, dict) else None)
    except FileNotFoundError:
        token = secrets.token_urlsafe(24)
        save_token(path, token)
        return token
    except (ValueError, TypeError) as error:
        raise ValueError('配对凭证损坏，请关闭接收器后使用 --reset-pairing 重置配对。') from error
