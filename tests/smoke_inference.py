"""Optional real-model smoke test. Synthetic scoreboard, not sports-accuracy validation."""
import json
import tempfile
from pathlib import Path
import cv2
import numpy as np
from service.vision import load_models, analyze

with tempfile.TemporaryDirectory() as directory:
    video = Path(directory)/'synthetic-scoreboard.mp4'
    writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'mp4v'),1,(640,360))
    assert writer.isOpened()
    for second in range(65):
        frame=np.zeros((360,640,3),dtype=np.uint8)
        clock=660-second
        for text,x in [('42',24),('41',145),('1',270),(f'{clock//60}:{clock%60:02}',385)]:
            cv2.putText(frame,text,(x,267),cv2.FONT_HERSHEY_SIMPLEX,1.2,(255,255,255),2,cv2.LINE_AA)
        writer.write(frame)
    writer.release()
    config={'sport':'nba','regions':{'home':[.03,.6,.14,.2],'away':[.22,.6,.14,.2],'period':[.4,.6,.12,.2],'clock':[.58,.6,.25,.2]}}
    result=analyze(video,config,lambda *_:None,load_models(download=False))
    assert result['rating'] is None,'A one-minute synthetic clip must not receive a final game rating'
    assert result['coverage']['accepted_observations']>=10,'OCR should read the synthetic scoreboard'
    assert len(result['vision_evidence'])>0,'Detector must run'
    print(json.dumps({'smoke_test':'passed','fixture':'synthetic scoreboard; not a real game','accepted_observations':result['coverage']['accepted_observations'],'detector_samples':len(result['vision_evidence']),'final_rating':result['rating'],'models_loaded':list(result['weights_sha256'])}))
