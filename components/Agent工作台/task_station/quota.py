"""Validated snapshots of visible Claude quota notices; no credentials or web scraping."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from urllib.parse import urlsplit
from credential_store import atomic_json

STATES = {'limited', 'available', 'unknown', 'login_required', 'read_failed'}


def timestamp(value):
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError('时间必须为带时区的ISO格式')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.utcoffset() is None:
            raise ValueError()
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise ValueError('时间必须为带时区的ISO格式') from None


class QuotaStore:
    def __init__(self, path, clock=None):
        self.path = Path(path)
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def validate(self, value):
        if not isinstance(value, dict) or type(value.get('schema_version')) is not int or value['schema_version'] != 1:
            raise ValueError('额度记录格式无效')
        if value.get('state') not in STATES:
            raise ValueError('额度状态无效')
        checked = timestamp(value.get('checked_at'))
        if checked > self.clock() + timedelta(minutes=5):
            raise ValueError('核对时间不能晚于当前时间')
        reset = value.get('reset_at')
        if reset is not None:
            timestamp(reset)
        source = value.get('source_url', '')
        if not isinstance(source, str) or len(source) > 500:
            raise ValueError('来源地址无效')
        try:
            parsed = urlsplit(source)
            valid = parsed.scheme == 'https' and parsed.hostname in ('claude.ai', 'www.claude.ai') and parsed.port in (None,443) and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment
        except ValueError:
            valid = False
        if not valid:
            raise ValueError('来源必须为Claude官方HTTPS页面')
        for field, limit in [('reset_text', 200), ('source_text', 1200)]:
            if not isinstance(value.get(field, ''), str) or len(value.get(field, '')) > limit:
                raise ValueError('额度记录文字过长或格式无效')
        return {key: value.get(key) for key in ('schema_version','state','checked_at','reset_at','source_url')} | {key:value.get(key,'') for key in ('reset_text','source_text')}

    def save(self, value):
        clean = self.validate(value)
        atomic_json(self.path, clean)
        return self.read()

    def read(self):
        if not self.path.exists():
            return dict(state='unknown', effective_state='unknown', checked_at=None, reset_at=None, reset_text='', source_text='尚未取得官网核对记录。', source_url='https://claude.ai/new')
        try:
            if self.path.stat().st_size > 16384:
                raise ValueError()
            value = self.validate(json.loads(self.path.read_text(encoding='utf-8-sig')))
            effective = value['state']
            if self.clock() - timestamp(value['checked_at']) > timedelta(hours=26):
                effective = 'stale'
            elif effective == 'limited' and value['reset_at'] and timestamp(value['reset_at']) <= self.clock():
                effective = 'due'
            return dict(value, effective_state=effective)
        except (OSError, ValueError, TypeError, KeyError):
            return dict(state='read_failed', effective_state='read_failed', checked_at=None, reset_at=None, reset_text='', source_text='额度记录无法读取，等待重新核对；不代表额度可用。', source_url='https://claude.ai/new')
