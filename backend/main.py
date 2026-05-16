import uuid
import threading
import subprocess
from pathlib import Path
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from inspection_core import Config, run

# ----------------------------
# CONFIG: set your model paths
# ----------------------------
DET_MODEL_PATH = Path(r"D:\YOLO_Project\best1.pt")  # detection + tracking
CLS_MODEL_PATH = Path(r"D:\YOLO_Project\best.pt")   # classification

BASE_DIR = Path(__file__).parent
OUTPUTS_DIR = BASE_DIR / "outputs"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)


def to_browser_mp4(src_mp4: Path, dst_mp4: Path) -> None:
    """
    Convert OpenCV's mp4 (often mp4v) into browser-friendly H.264 MP4.
    Requires ffmpeg installed and available on PATH.
    """
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src_mp4),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(dst_mp4),
        ],
        check=True,
    )


class StartRequest(BaseModel):
    video_path: str


class Job(BaseModel):
    id: str
    status: str  # queued | running | done | error
    error: Optional[str] = None
    output_video_url: Optional[str] = None
    output_csv_url: Optional[str] = None
#yolo is used

jobs: Dict[str, Job] = {}

app = FastAPI(title="Conveyor Inspection API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve backend/outputs/* as http://127.0.0.1:8000/outputs/*
app.mount("/outputs", StaticFiles(directory=str(OUTPUTS_DIR)), name="outputs")


@app.get("/")
def root():
    return {"ok": True, "docs": "/docs"}
#convyor belt inspection

def _run_job(job_id: str, video_path: Path) -> None:
    jobs[job_id] = Job(id=job_id, status="running")

    tmp_video = OUTPUTS_DIR / f"{job_id}_tmp.mp4"  # OpenCV output
    final_video = OUTPUTS_DIR / f"{job_id}.mp4"    # H.264 output for browser
    out_csv = OUTPUTS_DIR / f"{job_id}.csv"

    try:
        # validate model files early (better error message)
        if not DET_MODEL_PATH.exists():
            raise FileNotFoundError(f"Detection model not found: {DET_MODEL_PATH}")
        if not CLS_MODEL_PATH.exists():
            raise FileNotFoundError(f"Classification model not found: {CLS_MODEL_PATH}")

        cfg = Config(
            det_model_path=DET_MODEL_PATH,
            cls_model_path=CLS_MODEL_PATH,
            input_video=video_path,
            output_video=tmp_video,
            output_csv=out_csv,
            show_window=False,  # IMPORTANT for backend
        )

        run(cfg)

        if not tmp_video.exists():
            raise FileNotFoundError(f"Temp output video not found: {tmp_video}")

        # Convert to browser friendly MP4
        to_browser_mp4(tmp_video, final_video)

        if not final_video.exists():
            raise FileNotFoundError(f"H.264 output video not found: {final_video}")

        # Optional cleanup: remove temp file
        try:
            tmp_video.unlink()
        except Exception:
            pass

        jobs[job_id] = Job(
            id=job_id,
            status="done",
            error=None,
            output_video_url=f"/outputs/{final_video.name}",
            output_csv_url=f"/outputs/{out_csv.name}",
        )

    except Exception as e:
        jobs[job_id] = Job(id=job_id, status="error", error=str(e))


@app.post("/api/jobs", response_model=Job)
def start_job(req: StartRequest):
    video_path = Path(req.video_path.strip().strip('"'))

    if not video_path.exists():
        raise HTTPException(status_code=400, detail=f"Video not found: {video_path}")

    job_id = uuid.uuid4().hex
    jobs[job_id] = Job(id=job_id, status="queued")

    threading.Thread(target=_run_job, args=(job_id, video_path), daemon=True).start()
    return jobs[job_id]


@app.get("/api/jobs/{job_id}", response_model=Job)
def get_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job