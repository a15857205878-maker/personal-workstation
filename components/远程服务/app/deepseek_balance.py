"""Read official API balance without exposing credential material to the server."""
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import time
from deepseek_runner import harness_paths
from usage import UsageService,stop_process


MESSAGES={
    'missing_credentials':'未找到官方 API Key，请在电脑 DeepSeek Harness 中配置后重试。',
    'auth':'DeepSeek API 认证失败，请在电脑 Harness 中检查官方 API Key。',
    'network':'暂时无法查询 DeepSeek 余额，请检查电脑网络后重试。',
    'unavailable':'DeepSeek 余额暂时不可用，请稍后重试。',
    'invalid':'余额数据不完整，未显示金额；未知不代表余额为零。',
}

def money(value):
    return value if isinstance(value,str) and re.fullmatch(r'-?(?:0|[1-9]\d{0,14})(?:\.\d{1,12})?',value) else None


def normalize_balance(raw):
    result={'provider':'deepseek','status':'unavailable','balances':[],'is_available':None,
            'message':MESSAGES['invalid']}
    if not isinstance(raw,dict):return result
    if raw.get('error_code') in MESSAGES:
        result['message']=MESSAGES[raw['error_code']];return result
    rows=raw.get('balance_infos');balances=[];currencies=set()
    if not isinstance(rows,list) or not 1<=len(rows)<=2:return result
    for row in rows:
        if not isinstance(row,dict):return result
        currency=row.get('currency');total=money(row.get('total_balance'))
        if currency not in ('CNY','USD') or currency in currencies or total is None:return result
        currencies.add(currency)
        balances.append({'currency':currency,'total':total,'granted':money(row.get('granted_balance')),
                         'topped_up':money(row.get('topped_up_balance'))})
    result.update(status='available',balances=balances,
                  is_available=raw.get('is_available') if type(raw.get('is_available')) is bool else None,
                  message='当前 Harness 官方 API Key 账户余额；不同币种分别显示。')
    return result


class DeepSeekBalanceService(UsageService):
    def _read_balance(self):
        paths=harness_paths()
        if not paths:return {'error_code':'missing_credentials'}
        env=os.environ.copy();env['ELECTRON_RUN_AS_NODE']='1'
        process=self._spawn([str(paths[0]),'--expose-internals',str(Path(__file__).with_suffix('.cjs'))],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        try:
            output,_=process.communicate(timeout=15)
            if process.returncode or len(output)>16384:return {'error_code':'unavailable'}
            return json.loads(output)
        except subprocess.TimeoutExpired:
            process.kill();process.communicate();return {'error_code':'network'}
        finally:
            if process.poll() is None:stop_process(process)
            for stream in (process.stdin,process.stdout):
                if stream is not None:
                    try:stream.close()
                    except (OSError,ValueError):pass

    def read(self):
        with self.lock:
            if not self.closed and self.cached is not None and self.clock()<self.expires:
                return copy.deepcopy(dict(self.cached,cached=True))
            try:
                raw={'error_code':'unavailable'} if self.closed else self.probe() if self.probe is not None else self._read_balance()
                value=normalize_balance(raw)
            except Exception:value=normalize_balance({'error_code':'network'})
            finally:
                with self.process_lock:self.active=None
            self.cached=dict(value,checked_at=time.time(),cached=False);self.expires=self.clock()+30
            return copy.deepcopy(self.cached)
