"""Transport routing keeps API secrets away from the local Codex process."""
from provider_client import ProviderClient
from codex_channel import CodexChannel
from antigravity_channel import AntigravityChannel

class ModelChannels:
    def __init__(self,api=None,local=None,antigravity=None):self.api=api or ProviderClient();self.local=local or CodexChannel();self.antigravity=antigravity or AntigravityChannel()
    def _client(self,profile):return self.antigravity if profile['kind']=='antigravity_local' else self.local if profile['kind']=='codex_local' else self.api
    def complete(self,profile,key,*args):return self._client(profile).complete(profile,'' if profile['kind'] in ('codex_local','antigravity_local') else key,*args)
    def complete_json(self,profile,key,*args):
        if self._client(profile) is self.api:
            return getattr(self.api,'complete_json',self.api.complete)(profile,key,*args)
        return self.complete(profile,key,*args)
    def models(self,profile,key):return self._client(profile).models(profile,'' if profile['kind'] in ('codex_local','antigravity_local') else key)
    def interrupt(self):
        for client in (self.api,self.local,self.antigravity):
            method=getattr(client,'interrupt',None)
            if method:method()
