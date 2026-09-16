"""Explainable NBA rating from an OCR-derived game timeline, never from a filename."""
import hashlib
import json
import math
import re
from pathlib import Path

MODEL = {'version': 'nba-video-0.1.0', 'components': {'competitiveness': .50, 'momentum': .30, 'clutch': .20}, 'full_game_coverage_seconds': 2520, 'max_covered_gap_seconds': 60, 'minimum_ocr_confidence': .65}
MODEL_HASH = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def parse_score(text):
    text = text.strip().replace('O', '0').replace('o', '0')
    return int(text) if re.fullmatch(r'\d{1,3}', text) and int(text) <= 250 else None


def parse_period(text):
    text = re.sub(r'\s+', '', text.upper())
    match = re.fullmatch(r'(?:Q|QUARTER)?([1-4])(?:ST|ND|RD|TH)?', text)
    if match:
        return int(match[1])
    if text in ('OT', '1OT', 'OT1'):
        return 5
    match = re.fullmatch(r'(?:([2-4])OT|OT([2-4]))', text)
    return 4 + int(match[1] or match[2]) if match else None


def parse_clock(text):
    text = re.sub(r'\s+', '', text).replace('O', '0')
    # OCR can read the clock colon as a dot. Two trailing digits mean MM:SS; one is tenths.
    match = re.fullmatch(r'(\d{1,2})[:.](\d{2})(\.\d+)?', text)
    if match:
        minutes, seconds = int(match[1]), float(match[2] + (match[3] or ''))
        return minutes * 60 + seconds if minutes <= 12 and seconds < 60 else None
    # Broadcasts often show tenths only in the final minute.
    return float(text) if re.fullmatch(r'\d{1,2}\.\d', text) and float(text) < 60 else None


def observation(fields, video_time):
    values = {k: v[0] for k, v in fields.items()}
    confidence = min(float(v[1]) for v in fields.values())
    if confidence < MODEL['minimum_ocr_confidence']:
        return None
    home, away = parse_score(values['home']), parse_score(values['away'])
    period, clock = parse_period(values['period']), parse_clock(values['clock'])
    if None in (home, away, period, clock):
        return None
    length = 720 if period <= 4 else 300
    if clock > length:
        return None
    elapsed = (period - 1) * 720 + (720 - clock) if period <= 4 else 2880 + (period - 5) * 300 + (300 - clock)
    return {'video_time': round(video_time, 2), 'elapsed': elapsed, 'home': home, 'away': away, 'period': period, 'clock': clock, 'confidence': round(confidence, 3)}


def clean_timeline(observations):
    accepted, rejected = [], 0
    for row in observations:
        if not row:
            rejected += 1
            continue
        if accepted:
            last = accepted[-1]
            dt = row['elapsed'] - last['elapsed']
            dh, da = row['home'] - last['home'], row['away'] - last['away']
            # Reject replays, score regressions, implausible jumps and repeated overlays.
            if dt < 0 or dh < 0 or da < 0 or dh + da > max(4, dt / 2 + 2) or row['period'] > last['period'] + 1:
                rejected += 1
                continue
            if dt == 0 and dh + da == 0:
                continue
        accepted.append(row)
    return accepted, rejected


def rate(observations, sampled_frames, detections=None):
    rows, rejected = clean_timeline(observations)
    covered = closeness = clutch_time = clutch_close = 0.0
    lead_changes = ties = 0
    last_leader = 0
    evidence = []
    for i, row in enumerate(rows):
        margin = row['home'] - row['away']
        leader = 1 if margin > 0 else -1 if margin < 0 else 0
        if i:
            prev = rows[i-1]
            dt = row['elapsed'] - prev['elapsed']
            if 0 < dt <= MODEL['max_covered_gap_seconds'] and row['period'] == prev['period']:
                covered += dt
                closeness += dt * max(0, 1 - abs(prev['home'] - prev['away']) / 20)
                if row['elapsed'] >= 2580:
                    clutch_time += dt
                    clutch_close += dt * max(0, 1 - abs(prev['home'] - prev['away']) / 10)
            if row['home'] + row['away'] > prev['home'] + prev['away']:
                if leader and last_leader and leader != last_leader:
                    lead_changes += 1
                    evidence.append({'video_time': row['video_time'], 'description': f"Observed lead change: {row['home']}–{row['away']}."})
                if not leader and prev['home'] != prev['away']:
                    ties += 1
        if leader:
            last_leader = leader
    periods = sorted({r['period'] for r in rows})
    complete = bool(rows and rows[0]['period'] == 1 and rows[0]['clock'] >= 660 and rows[-1]['period'] >= 4 and rows[-1]['clock'] <= 10 and rows[-1]['home'] != rows[-1]['away'] and set(range(1, rows[-1]['period']+1)).issubset(periods) and covered >= MODEL['full_game_coverage_seconds'] and clutch_time >= 240)
    components = []
    if covered:
        components = [
            {'name': 'Competitiveness', 'score': round(1 + 9 * closeness / covered, 1), 'weight': .5, 'detail': f'{covered / 60:.1f} minutes of game-clock coverage; narrower margins score higher.'},
            {'name': 'Momentum', 'score': round(1 + 9 * min(1, (lead_changes + .5 * ties) / 20), 1), 'weight': .3, 'detail': f'{lead_changes} observed lead changes and {ties} new ties. Sampling can miss fast changes.'},
            {'name': 'Clutch finish', 'score': round(1 + 9 * clutch_close / clutch_time, 1) if clutch_time else None, 'weight': .2, 'detail': f'{clutch_time / 60:.1f} minutes observed in the final five regulation minutes and overtime.'}]
    available = [c for c in components if c['score'] is not None]
    provisional = round(sum(c['score'] * c['weight'] for c in available) / sum(c['weight'] for c in available), 1) if covered >= 900 and available else None
    reason = 'Coverage checks passed. Experimental video-derived rating; game completion is inferred from the visible clock, not an official final signal.' if complete else 'Final rating withheld: the video must cover all quarters, the opening minute and closing seconds, with at least 42 minutes of readable game-clock coverage and four minutes of the closing period.'
    return {'model': MODEL['version'], 'model_hash': MODEL_HASH, 'rating': provisional if complete else None, 'provisional_rating': provisional, 'coverage_checks_passed': complete, 'reason': reason, 'coverage': {'game_clock_minutes': round(covered/60, 2), 'periods': periods, 'accepted_observations': len(rows), 'sampled_frames': sampled_frames, 'rejected_observations': rejected, 'average_ocr_confidence': round(sum(r['confidence'] for r in rows)/len(rows), 3) if rows else None}, 'components': components, 'key_moments': evidence[:100], 'vision_evidence': detections or [], 'timeline': rows, 'limitations': ['Not trained on human game-quality labels; the rating head is an explicit formula.', 'Pretrained OCR and object detection are not validated basketball action recognition.', 'Crowd emotion, tactical quality, player identities, stakes and official results are not inferred.', 'Sampled video can miss scoring changes, replays and corrected scores. Do not use this experimental result to settle wagers.']}
