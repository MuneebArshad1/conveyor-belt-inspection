import uuid
from pathlib import Path
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from inspection_core import Config, run

DET_MODEL_PATH = Path(r"D:\YOLO_Project\best1.pt")
CLS_MODEL_PATH = Path(r"D:\YOLO_Project\best.pt")

BASE_DIR = Path(__file__).parent
OUTPUTS_DIR = BASE_DIR / "outputs"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

import subprocess
from pathlib import Path

def to_browser_mp4(src_mp4: Path, dst_mp4: Path) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(src_mp4),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(dst_mp4),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )


class StartRequest(BaseModel):
    video_path: str


class Job(BaseModel):
    id: str
    status: str  # queued | running | done | error
    error: Optional[str] = None
    output_video_url: Optional[str] = None
    output_csv_url: Optional[str] = None


jobs: Dict[str, Job] = {}

app = FastAPI(title="Conveyor Inspection API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/outputs", StaticFiles(directory=str(OUTPUTS_DIR)), name="outputs")


def _run_job(job_id: str, video_path: Path) -> None:
    jobs[job_id] = Job(id=job_id, status="running")

    out_video = OUTPUTS_DIR / f"{job_id}.mp4"
    out_csv = OUTPUTS_DIR / f"{job_id}.csv"

    try:
        cfg = Config(
            det_model_path=DET_MODEL_PATH,
            cls_model_path=CLS_MODEL_PATH,
            input_video=video_path,
            output_video=out_video,
            output_csv=out_csv,
            show_window=False,  # IMPORTANT for backend
        )
        run(cfg)
        jobs[job_id] = Job(
            id=job_id,
            status="done",
            output_video_url=f"/outputs/{out_video.name}",
            output_csv_url=f"/outputs/{out_csv.name}",
        )

        tmp_video = out_video  # current OpenCV mp4v output
        final_video = OUTPUTS_DIR / f"{job_id}_h264.mp4"

        to_browser_mp4(tmp_video, final_video)

        jobs[job_id] = Job(
            id=job_id,
            status="done",
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

    # simple background thread
    import threading
    threading.Thread(target=_run_job, args=(job_id, video_path), daemon=True).start()

    return jobs[job_id]


@app.get("/api/jobs/{job_id}", response_model=Job)
def get_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job