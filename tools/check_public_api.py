"""Read-only HTTPS/CORS/data preflight; never disables certificate verification."""
import argparse
import json
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def check_cors(headers, origin, preflight=False):
    if headers.get('Access-Control-Allow-Origin') != origin:
        raise ValueError('CORS_ORIGIN_MISSING')
    if preflight:
        methods = {s.strip().upper() for s in headers.get('Access-Control-Allow-Methods', '').split(',')}
        allowed = {s.strip().lower() for s in headers.get('Access-Control-Allow-Headers', '').split(',')}
        if 'POST' not in methods or not {'content-type', 'x-research-version'} <= allowed:
            raise ValueError('CORS_PREFLIGHT_INCOMPLETE')


def probe(base, origin, path, preflight=False):
    headers = {'Origin': origin, 'Accept': 'application/json'}
    if preflight:
        headers.update({'Access-Control-Request-Method': 'POST',
                        'Access-Control-Request-Headers': 'content-type,x-research-version'})
    request = Request(base + path, headers=headers, method='OPTIONS' if preflight else 'GET')
    with urlopen(request, timeout=15, context=ssl.create_default_context()) as response:
        check_cors(response.headers, origin, preflight)
        if preflight:
            return {'path': path, 'method': 'OPTIONS', 'httpStatus': response.status, 'ok': True}
        if 'application/json' not in response.headers.get('Content-Type', ''):
            raise ValueError('NOT_JSON')
        payload = json.loads(response.read(2_000_001))
        if not isinstance(payload, dict):
            raise ValueError('INVALID_RESPONSE')
        if path in ('/assets?limit=1&offset=0', '/strategies') and not payload.get('items'):
            raise ValueError('EMPTY_CATALOG')
        if path == '/data/status' and payload.get('status') not in ('ready', 'stale', 'updating', 'failed'):
            raise ValueError('INVALID_DATA_STATUS')
        if path == '/market/overview' and not payload.get('tradeDate'):
            raise ValueError('MISSING_TRADE_DATE')
        return {'path': path, 'method': 'GET', 'httpStatus': response.status, 'ok': True,
                **{key: payload[key] for key in ('tradeDate', 'latestTradeDate', 'assetCount', 'status') if key in payload}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--origin', required=True)
    args = parser.parse_args()
    base = args.base_url.rstrip('/')
    for value in (base, args.origin):
        parsed = urlsplit(value)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            parser.error('Use public HTTPS URLs without credentials, queries or fragments')
    paths = [('/health', False), ('/data/status', False), ('/assets?limit=1&offset=0', False),
             ('/strategies', False), ('/market/overview', False), ('/data/capability', True)]
    failed = False
    for path, options in paths:
        try:
            print(json.dumps(probe(base, args.origin, path, options), ensure_ascii=False), flush=True)
        except (HTTPError, URLError, ValueError, TimeoutError) as error:
            failed = True
            reason = error.reason if isinstance(error, URLError) else error
            kind = 'TLS_VERIFICATION_FAILED' if isinstance(reason, ssl.SSLCertVerificationError) else type(error).__name__
            print(json.dumps({'path': path, 'ok': False, 'error': kind, 'detail': str(reason)}, ensure_ascii=False), flush=True)
            if isinstance(error, URLError) and not isinstance(error, HTTPError):
                break
    raise SystemExit(1 if failed else 0)


if __name__ == '__main__':
    main()
