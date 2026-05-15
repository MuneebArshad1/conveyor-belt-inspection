import { useEffect, useMemo, useState } from "react";
import "./App.css";

const API_BASE = "http://localhost:8000";

export default function App() {
  const [videoPath, setVideoPath] = useState("");
  const [job, setJob] = useState(null);
  const [err, setErr] = useState("");

  const outputVideoUrl = useMemo(() => {
    if (!job?.output_video_url) return "";
    return API_BASE + job.output_video_url;
  }, [job]);

  const outputCsvUrl = useMemo(() => {
    if (!job?.output_csv_url) return "";
    return API_BASE + job.output_csv_url;
  }, [job]);

  async function start() {
    setErr("");
    setJob(null);

    try {
      const res = await fetch(`${API_BASE}/api/jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ video_path: videoPath }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data?.detail || "Failed to start job");
      }

      const data = await res.json();
      setJob(data);
    } catch (e) {
      setErr(String(e.message || e));
    }
  }

  useEffect(() => {
    if (!job?.id) return;
    if (job.status === "done" || job.status === "error") return;

    const t = setInterval(async () => {
      const res = await fetch(`${API_BASE}/api/jobs/${job.id}`);
      const data = await res.json();
      setJob(data);
    }, 1000);

    return () => clearInterval(t);
  }, [job?.id, job?.status]);

  return (
    <div className="page">
      <div className="card">
        <h1>Conveyor Box Inspection</h1>
        <p className="sub">
          Enter a video path (on the same machine running the backend), then start inspection.
        </p>

        <div className="row">
          <input
            value={videoPath}
            onChange={(e) => setVideoPath(e.target.value)}
            placeholder='Example: D:\videos\input.mp4'
          />
          <button onClick={start} disabled={!videoPath.trim() || job?.status === "running"}>
            {job?.status === "running" ? "Running..." : "Start"}
          </button>
        </div>

        {err ? <div className="error">{err}</div> : null}

        {job ? (
          <div className="status">
            <div><b>Job:</b> {job.id}</div>
            <div>
              <b>Status:</b>{" "}
              <span className={`pill ${job.status}`}>{job.status}</span>
            </div>
            {job.error ? <div className="error">{job.error}</div> : null}
          </div>
        ) : null}

        {job?.status === "done" ? (
          <div className="results">
            <h2>Result</h2>
            <video src={outputVideoUrl} controls style={{ width: "100%", borderRadius: 12 }} />
            <div className="links">
              <a href={outputCsvUrl} target="_blank" rel="noreferrer">Download CSV</a>
              <a href={outputVideoUrl} target="_blank" rel="noreferrer">Open video</a>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}