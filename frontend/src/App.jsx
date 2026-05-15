import { useEffect, useMemo, useState } from "react";
import "./App.css";

import img1 from "./assets/1.png";
import img2 from "./assets/2.jpg";
import img3 from "./assets/3.jpg";
import img4 from "./assets/4.jpg";

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

  const status = job?.status || "idle";

  return (
    <div className="app">
      <div className="bg" aria-hidden="true" />

      <header className="hero">
        <div className="heroInner">
          <div className="brand">
            <div className="brandMark" aria-hidden="true">
              <span />
              <span />
              <span />
            </div>

            <div className="brandText">
              <p className="kicker">AI Vision on Production Line</p>
              <h1>Production Line Inspection</h1>
              <p className="sub">
                Tracker, Counter, Damage Classifier, Output Video Generator
              </p>
            </div>
          </div>

          <div className="mosaic" aria-label="Industry imagery">
            <img className="m1" src={img1} alt="Conveyor inspection scene 1" />
            <img className="m2" src={img2} alt="Conveyor inspection scene 2" />
            <img className="m3" src={img3} alt="Conveyor inspection scene 3" />
            <img className="m4" src={img4} alt="Conveyor inspection scene 4" />
          </div>
        </div>
      </header>

      <main className="main">
        <section className="panel">
          <div className="panelHeader">
            <h2>Run Inspection</h2>
            <div className={`statusPill ${status}`}>
              <span className="dot" />
              <span className="label">{status}</span>
            </div>
          </div>

          <p className="hint">
            Enter a video path (on the same machine running the backend). Use forward slashes or
            double backslashes in JSON.
          </p>

          <div className="row">
            <div className="field">
              <label>Video path</label>
              <input
                value={videoPath}
                onChange={(e) => setVideoPath(e.target.value)}
                placeholder="Example: D:/videos/input.mp4"
              />
            </div>

            <button
              className="primary"
              onClick={start}
              disabled={!videoPath.trim() || job?.status === "running"}
            >
              {job?.status === "running" ? "Processing…" : "Start"}
            </button>
          </div>

          {err ? (
            <div className="alert error">
              <div className="alertTitle">Request failed</div>
              <div className="alertBody">{err}</div>
            </div>
          ) : null}

          {job ? (
            <div className="meta">
              <div className="metaRow">
                <span className="metaKey">Job ID</span>
                <span className="mono">{job.id}</span>
              </div>

              {job.error ? (
                <div className="alert error">
                  <div className="alertTitle">Processing error</div>
                  <div className="alertBody mono">{job.error}</div>
                </div>
              ) : null}
            </div>
          ) : null}
        </section>

        <section className="panel">
          <div className="panelHeader">
            <h2>Output</h2>
            <p className="panelNote">When complete, the processed video plays here.</p>
          </div>

          {job?.status === "done" ? (
            <>
              <div className="videoShell">
                <video className="video" src={outputVideoUrl} controls playsInline />
              </div>

              <div className="actions">
                <a className="btn" href={outputCsvUrl} target="_blank" rel="noreferrer">
                  Download CSV
                </a>
                <a className="btn ghost" href={outputVideoUrl} target="_blank" rel="noreferrer">
                  Open video
                </a>
              </div>
            </>
          ) : (
            <div className="empty">
              <div className="emptyTitle">No output yet</div>
              <div className="emptyBody">
                Start a job to generate a processed video and CSV report.
              </div>
            </div>
          )}
        </section>
      </main>

      <footer className="footer">
        <span>FastAPI + React • Local demo</span>
        <span className="sep">•</span>
        <a href={`${API_BASE}/docs`} target="_blank" rel="noreferrer">
          API Docs
        </a>
      </footer>
    </div>
  );
}