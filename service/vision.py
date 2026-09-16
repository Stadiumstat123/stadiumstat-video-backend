import hashlib
import json
import os
from pathlib import Path


def load_models(download=False):
    import easyocr
    import torch
    from torchvision.models.detection import ssdlite320_mobilenet_v3_large, SSDLite320_MobileNet_V3_Large_Weights
    torch.set_num_threads(int(os.environ.get('TORCH_THREADS', '4')))
    root = Path(os.environ.get('MODEL_DIR', '/models'))
    root.mkdir(parents=True, exist_ok=True)
    checkpoint = root / 'ssdlite320-coco.pth'
    if download:
        weights = SSDLite320_MobileNet_V3_Large_Weights.DEFAULT
        torch.save(weights.get_state_dict(progress=True, check_hash=True), checkpoint)
    if not checkpoint.exists():
        raise RuntimeError('Vision weights missing. Run python -m service.prepare before starting inference.')
    device = 'cuda' if torch.cuda.is_available() and os.environ.get('DEVICE', 'auto') != 'cpu' else 'cpu'
    detector = ssdlite320_mobilenet_v3_large(weights=None, weights_backbone=None)
    detector.load_state_dict(torch.load(checkpoint, map_location='cpu', weights_only=True))
    detector.to(device).eval()
    reader = easyocr.Reader(['en'], gpu=device == 'cuda', model_storage_directory=str(root / 'easyocr'), download_enabled=download, verbose=False)
    hashes = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*.pth')}
    return reader, detector, device, hashes


def analyze(path, config, progress, models):
    import cv2
    import torch
    from torchvision.transforms.functional import to_tensor
    from .scoring import observation, rate
    reader, detector, device, hashes = models
    cap = cv2.VideoCapture(str(path))
    try:
        fps, frames = cap.get(cv2.CAP_PROP_FPS), cap.get(cv2.CAP_PROP_FRAME_COUNT)
        if fps <= 0 or frames <= 0:
            raise ValueError('Video could not be decoded.')
        duration = frames / fps
        if not 60 <= duration <= 14400:
            raise ValueError('Use a video between one minute and four hours.')
        interval = 5.0
        observations, detections = [], []
        count = 0
        for index in range(int(duration // interval) + 1):
            timestamp = index * interval
            cap.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
            ok, frame = cap.read()
            if not ok:
                continue
            count += 1
            height, width = frame.shape[:2]
            fields = {}
            for name, box in config['regions'].items():
                x, y, w, h = box
                crop = frame[int(y*height):int((y+h)*height), int(x*width):int((x+w)*width)]
                if not crop.size:
                    fields[name] = ('', 0)
                    continue
                crop = cv2.resize(crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
                alphabet = '0123456789:.' if name != 'period' else '0123456789QqOTotSTstNDndRDrdTHth '
                result = reader.recognize(crop, horizontal_list=[[0, crop.shape[1], 0, crop.shape[0]]], free_list=[], allowlist=alphabet, detail=1, paragraph=False)
                result.sort(key=lambda r: min(p[0] for p in r[0]))
                fields[name] = (''.join(r[1] for r in result), min((float(r[2]) for r in result), default=0))
            observations.append(observation(fields, timestamp))
            if index % 6 == 0:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                with torch.inference_mode():
                    detected = detector([to_tensor(rgb).to(device)])[0]
                labels, scores = detected['labels'].cpu().tolist(), detected['scores'].cpu().tolist()
                detections.append({'video_time': timestamp, 'people': sum(l == 1 and s >= .5 for l, s in zip(labels, scores)), 'sports_balls': sum(l == 37 and s >= .35 for l, s in zip(labels, scores)), 'note': 'Generic COCO detections; not player identification or proof of a basketball play.'})
            progress(min(99, int(timestamp / duration * 100)), f'Analyzing {int(timestamp // 60)} of {int(duration // 60)} video minutes')
        result = rate(observations, count, detections)
        result['weights_sha256'] = hashes
        result['configuration'] = config
        result['pipeline_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        result['runtime_versions'] = {'torch': torch.__version__, 'opencv': cv2.__version__}
        result['video_duration_seconds'] = round(duration, 2)
        result['sample_interval_seconds'] = interval
        return result
    finally:
        cap.release()
