import json
import shutil
import time
from .storage import ROOT, connect, update
from .vision import load_models, analyze


def progress(job, pct, msg):
    update(job, progress=pct, message=msg)
    with connect() as db:
        db.execute('INSERT OR REPLACE INTO runtime VALUES (1,?,1)', (int(time.time()),))


def main():
    # Run exactly one worker with this SQLite deployment. A process restart retries its unfinished job.
    with connect() as db:
        db.execute('INSERT OR REPLACE INTO runtime VALUES (1,?,0)', (int(time.time()),))
        db.execute("UPDATE jobs SET state='queued',message='Retrying after worker restart' WHERE state='running'")
    models = load_models(download=False)
    while True:
        now = int(time.time())
        with connect() as db:
            db.execute('INSERT OR REPLACE INTO runtime VALUES (1,?,1)', (now,))
            # Interrupted uploads and expired results must not accumulate indefinitely.
            stale = db.execute("SELECT id FROM jobs WHERE (state='uploading' AND updated_at<?) OR (state IN ('completed','failed') AND updated_at<?)", (now-7200,now-30*86400)).fetchall()
            for row in stale:
                shutil.rmtree(ROOT/row['id'], ignore_errors=True)
                db.execute('DELETE FROM jobs WHERE id=?', (row['id'],))
            db.execute('BEGIN IMMEDIATE') if not db.in_transaction else None
            row = db.execute("SELECT * FROM jobs WHERE state='queued' ORDER BY created_at LIMIT 1").fetchone()
            if row:
                db.execute("UPDATE jobs SET state='running',message='Reading video with local vision models' WHERE id=? AND state='queued'", (row['id'],))
        if not row:
            time.sleep(2)
            continue
        job = row['id']
        try:
            result = analyze(ROOT/job/'video.bin', json.loads(row['config']), lambda pct,msg: progress(job,pct,msg), models)
            result['video_sha256'] = row['video_hash']
            update(job, state='completed', progress=100, result=json.dumps(result), message='Analysis complete' if result['rating'] is not None else 'Analysis complete; insufficient evidence for a final rating')
        except Exception as exc:
            print('Analysis failed', job, type(exc).__name__, flush=True)
            update(job, state='failed', message='Video could not be analyzed. Check the format, duration, and selected scoreboard regions.')
        finally:
            shutil.rmtree(ROOT/job, ignore_errors=True)


if __name__ == '__main__':
    main()
