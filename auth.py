import base64
import hashlib
import hmac
import json
import os
import time
import uuid


def verify(token, scope, job=None):
    if len(token) > 4096:
        raise ValueError('Invalid token')
    secret = os.environ.get('VIDEO_SERVICE_SECRET', '')
    if len(secret) < 32:
        raise ValueError('Service secret is not configured')
    payload, signature = token.split('.')
    actual = base64.urlsafe_b64decode(signature + '=' * (-len(signature) % 4))
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(actual, expected):
        raise ValueError('Invalid signature')
    claims = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
    now = time.time()
    if claims.get('scope') != scope or not now < claims.get('exp', 0) <= now + 3660:
        raise ValueError('Expired or invalid scope')
    if not isinstance(claims.get('sub'), str) or len(claims['sub']) != 64:
        raise ValueError('Invalid owner')
    if str(uuid.UUID(claims.get('job', ''))) != claims['job'] or (job and job != claims['job']):
        raise ValueError('Invalid job')
    return claims


def validate_config(config):
    if config.get('sport') != 'nba' or set(config.get('regions', {})) != {'home', 'away', 'period', 'clock'}:
        raise ValueError('NBA and four scoreboard regions are required')
    for box in config['regions'].values():
        if not isinstance(box, list) or len(box) != 4 or any(not isinstance(v, (float, int)) or isinstance(v, bool) for v in box):
            raise ValueError('Invalid scoreboard region')
        x, y, w, h = box
        if not (0 <= x < 1 and 0 <= y < 1 and .002 <= w <= .5 and .002 <= h <= .3 and x + w <= 1.000001 and y + h <= 1.000001):
            raise ValueError('Scoreboard region is out of bounds')
    return config
