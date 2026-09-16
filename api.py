import hashlib
import json
import os
import shutil
import time
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from .auth import verify, validate_config
from .storage import ROOT, connect, update

app = FastAPI(title='StadiumStat Independent Video Analysis', version='0.1.0')
origins = [x.strip() for x in os.environ.get('ALLOWED_ORIGINS', '').split(',') if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=['PUT', 'GET', 'DELETE'], allow_headers=['Authorization', 'Content-Type'], max_age=600)
MAX_BYTES = 8 * 1024**3


def claims(request, scope, job):
    token = request.headers.get('authorization', '').removeprefix('Bearer ')
    try:
        return verify(token, scope, job)
    except (ValueError, TypeError, KeyError):
        raise HTTPException(401, 'Invalid or expired analysis ticket')


def owned(job, owner):
    with connect() as db:
        row = db.execute('SELECT * FROM jobs WHERE id=? AND owner=?', (job, owner)).fetchone()
    if not row:
        raise HTTPException(404, 'Analysis not found')
    return row


@app.get('/health')
def health():
    with connect() as db:
        row = db.execute('SELECT * FROM runtime WHERE id=1').fetchone()
    ready = bool(row and row['ready'] and time.time() - row['heartbeat'] < 180)
    return {'ready': ready, 'model': 'nba-video-0.1.0', 'message': 'Local vision worker ready' if ready else 'Vision worker is starting, offline, or missing model weights'}


@app.put('/v1/uploads/{job}')
async def upload(job: str, request: Request):
    ticket = claims(request, 'upload', job)
    try:
        config = validate_config(ticket['config'])
        size = int(ticket['size'])
        if not 0 < size <= MAX_BYTES:
            raise ValueError('Invalid file size')
    except (ValueError, KeyError, TypeError):
        raise HTTPException(400, 'Invalid analysis configuration')
    if not health()['ready']:
        raise HTTPException(503, 'Vision worker is not ready. No upload was accepted.')
    ROOT.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(ROOT).free < size + 1024**3:
        raise HTTPException(507, 'Not enough analysis storage')
    now = int(time.time())
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT id FROM jobs WHERE id=?', (job,)).fetchone():
            raise HTTPException(409, 'This upload ticket was already used')
        active = db.execute("SELECT COUNT(*) FROM jobs WHERE state IN ('uploading','queued','running')").fetchone()[0]
        own = db.execute("SELECT COUNT(*) FROM jobs WHERE owner=? AND state IN ('uploading','queued','running')", (ticket['sub'],)).fetchone()[0]
        if active >= 4 or own >= 2:
            raise HTTPException(429, 'Analysis queue is full. Try again after a job finishes.')
        db.execute('INSERT INTO jobs(id,owner,state,config,created_at,updated_at) VALUES (?,?,?,?,?,?)', (job,ticket['sub'],'uploading',json.dumps(config),now,now))
    directory = ROOT / job
    directory.mkdir(exist_ok=False)
    video = directory / 'video.bin'
    digest, count = hashlib.sha256(), 0
    try:
        with video.open('wb') as handle:
            async for chunk in request.stream():
                count += len(chunk)
                if count > size or count > MAX_BYTES:
                    raise HTTPException(413, 'Video exceeds its declared size')
                handle.write(chunk)
                digest.update(chunk)
        if count != size:
            raise HTTPException(400, 'Upload was incomplete')
        update(job, state='queued', bytes=count, video_hash=digest.hexdigest(), message='Queued for local vision inference')
        return {'id': job, 'state': 'queued'}
    except BaseException:
        update(job, state='failed', message='Upload interrupted or invalid. Upload the file again with a new ticket.')
        shutil.rmtree(directory, ignore_errors=True)
        raise


@app.get('/v1/jobs/{job}')
def get_job(job: str, request: Request):
    row = owned(job, claims(request, 'read', job)['sub'])
    return {k: (json.loads(row[k]) if row[k] else None) if k == 'result' else row[k] for k in ['id', 'state', 'progress', 'message', 'result', 'created_at', 'updated_at']}


@app.delete('/v1/jobs/{job}')
def delete_job(job: str, request: Request):
    owner = claims(request, 'delete', job)['sub']
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT state FROM jobs WHERE id=? AND owner=?', (job,owner)).fetchone()
        if not row:
            raise HTTPException(404, 'Analysis not found')
        if row['state'] in ('running','uploading'):
            raise HTTPException(409, 'Wait for the active upload or analysis to finish before deleting it')
        db.execute('DELETE FROM jobs WHERE id=? AND owner=?', (job,owner))
    shutil.rmtree(ROOT/job, ignore_errors=True)
    return {'deleted': True}
