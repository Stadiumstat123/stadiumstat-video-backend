# StadiumStat independent video backend

This service runs pretrained EasyOCR and Torchvision SSDLite models locally. No ChatGPT, OpenAI API key, ESPN endpoint, or hosted LLM is used during video inference. Model weights are downloaded during image preparation; inference uses local files only.

**Implementation status:** service and website integration are provided. Real pretrained weights loaded and ran successfully against a synthetic scoreboard clip; API authentication, ownership, incomplete-upload and scoring-gate tests passed. No real full-game accuracy claim is made. A separately hosted inference server and a real uploaded NBA broadcast are required for an end-to-end validation. Do not describe the quality model as trained or validated on sports fan judgments: its final rating layer is a versioned formula on a computer-vision-derived timeline.

## What it does

1. Accepts a full video as a streamed, authenticated upload (maximum 8 GiB, one minute to four hours).
2. Reads four user-selected scoreboard regions: home score, away score, period and game clock.
3. Uses a pretrained neural OCR model every five video seconds and a generic person/ball detector every thirty seconds.
4. Filters replay clocks, score regressions and implausible score jumps; computes competitiveness, observed momentum and late-game closeness.
5. Returns a 1–10 experimental rating only after minimum coverage checks pass. Otherwise returns an explanation and, where enough footage is readable, a clearly provisional score.
6. Saves evidence timestamps, OCR confidence, weight hashes, scorer hash, video SHA-256 and components with the result. Generic detections are supporting evidence; they are not treated as proof of dunks, tactics or player performance.

This initial pipeline supports NBA regulation and overtime scoreboard conventions, not other leagues, football or live broadcast ingestion. User-selected regions must remain in the same location throughout the video. A final result is inferred from coverage, not an official final status. It is unsuitable for market settlement.

## Run on an independent server

Install Docker and Compose on a machine with at least 4 CPU cores, 8 GB RAM and sufficient durable disk space. CPU processing can be slower than video playback; a GPU deployment requires a matching CUDA PyTorch installation. Capacity figures are starting configurations, not benchmark guarantees.

Set environment variables outside source control:

- `VIDEO_SERVICE_SECRET`: a randomly generated secret, at least 32 characters.
- `ALLOWED_ORIGINS`: exact deployed website origin, e.g. `https://courtvision-nba-analyzer.nqc5464.chatgpt.site`.

Then run `docker compose up --build -d` from this directory. The build downloads weights. The service listens only on localhost port 8000; place an HTTPS reverse proxy in front of it, with streaming request bodies, an upload size limit of 8 GiB, and suitable timeouts. Do not put a public CDN request-size limit below the intended upload size.

Check `/health`: `ready` must be true before accepting uploads. A persistent `video_data` volume stores jobs and results. Run exactly one inference worker in this deployment. Replace the SQLite queue with a dedicated queue/object store before horizontal scaling.

## Connect to the website

Set these production Site environment values, then redeploy the Site:

- `VIDEO_ANALYZER_URL`: HTTPS origin of the independent service, without a trailing path.
- `VIDEO_SERVICE_SECRET`: same secret, marked secret.

The Site signs short-lived, job-specific upload tickets after ChatGPT **sign-in** (identity only). The video itself uploads directly to your server, not to ChatGPT. Status/results and deletion are authorized by the Site using owner-bound read/delete tickets. Existing practice wagers remain tied to their original data-feed scoring model; video results never replace their settlement score.

Open `/video.html`, choose a file, seek to a clear scoreboard, capture a frame and mark its four regions. Submit and monitor the analysis. Download evidence JSON after completion. Raw videos are deleted after success or failure; interrupted uploads expire after two hours. Results expire after thirty days. Storage cleanup runs while the inference worker is healthy; backups and provider retention must be configured separately.

## Boundaries and next training step

This is a functioning inference pipeline implementation, not a newly trained foundation model. Validate OCR and clock reconstruction on labeled broadcasts before claiming accuracy. A proprietary learned rating head would require licensed game footage and independent human ratings, then train/validation/test separation by game and season. No weights trained on unavailable labels are fabricated here.

The pretrained detector is generic COCO detection and cannot reliably track a small basketball at every camera distance. OCR quality depends on resolution, graphics and compression. No player identity, crowd emotion, foul correctness, tactical quality or historical stakes is inferred.

Tests: `python -m unittest discover -s tests` (API tests additionally need FastAPI and httpx). Docker build and actual neural inference require the full requirements and downloaded weights. Verify third-party model/data terms before commercial distribution.

Primary documentation: https://docs.pytorch.org/vision/stable/models/generated/torchvision.models.detection.ssdlite320_mobilenet_v3_large.html ; https://www.jaided.ai/easyocr/documentation/ ; https://fastapi.tiangolo.com/

## Railway deployment preparation

Deploy this directory as the Railway service source (not the full website checkout). The included `railway.json` uses the Dockerfile and `/health`. Attach a persistent volume at `/data`, configure its write permissions for the container user, and set `VIDEO_SERVICE_SECRET` and `ALLOWED_ORIGINS`. The startup script honors Railway’s `PORT`. Keep one replica because this package has one SQLite job queue and worker. No Railway service has been created by this configuration file alone.

The website now also supports private multipart uploads independently of this inference service. Stored videos are not automatically submitted to the inference service. Users can download the original and submit it through Upload & analyze once inference is connected.
