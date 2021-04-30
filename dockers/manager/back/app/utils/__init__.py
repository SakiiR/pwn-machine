from base64 import b64decode, b64encode
import json as JSON
from .registration import registerMutation, registerQuery, createType, createInterface



def base64_encode(s, json=False):
    if json:
        s = JSON.dumps(s)
    return b64encode(s.encode()).decode()

def base64_decode(s, json=False):
    r = b64decode(s.encode()).decode()
    if not json:
        return r
    try:
        return JSON.loads(r)
    except:
        return None


def create_kv_resolver(key):
    def resolve_kv(target, *_):
        kv = target.get(key, {})
        return [{"key": k, "value": v} for k, v in kv.items()]
    return resolve_kv