from __future__ import annotations

import csv
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Literal, Optional, Tuple
from collections import defaultdict

import cv2
from tqdm import tqdm
from ultralytics import YOLO

Label = Literal["damaged", "undamaged"]


@dataclass(frozen=True)
class Config:
    det_model_path: Path
    cls_model_path: Path
    input_video: Path
    output_video: Path
    output_csv: Path

    det_conf: float = 0.40
    cls_conf: float = 0.55
    vote_frames: int = 7
    lock_threshold: float = 0.60
    crop_padding: int = 8

    show_window: bool = False
    window_name: str = "Conveyor Inspection"
    quit_key: str = "q"

    color_damaged: Tuple[int, int, int] = (0, 60, 220)
    color_ok: Tuple[int, int, int] = (30, 200, 50)
    color_pending: Tuple[int, int, int] = (180, 180, 0)
    color_overlay: Tuple[int, int, int] = (15, 15, 15)

    font: int = cv2.FONT_HERSHEY_DUPLEX


def pad_crop(frame, x1: int, y1: int, x2: int, y2: int, pad: int):
    h, w = frame.shape[:2]
    px1 = max(0, x1 - pad)
    py1 = max(0, y1 - pad)
    px2 = min(w, x2 + pad)
    py2 = min(h, y2 + pad)
    return frame[py1:py2, px1:px2]


def draw_rounded_rect(
    img,
    pt1: Tuple[int, int],
    pt2: Tuple[int, int],
    color: Tuple[int, int, int],
    thickness: int = 2,
    radius: int = 10,
) -> None:
    x1, y1 = pt1
    x2, y2 = pt2
    r = max(0, min(radius, abs(x2 - x1) // 2, abs(y2 - y1) // 2))

    cv2.line(img, (x1 + r, y1), (x2 - r, y1), color, thickness)
    cv2.line(img, (x1 + r, y2), (x2 - r, y2), color, thickness)
    cv2.line(img, (x1, y1 + r), (x1, y2 - r), color, thickness)
    cv2.line(img, (x2, y1 + r), (x2, y2 - r), color, thickness)

    cv2.ellipse(img, (x1 + r, y1 + r), (r, r), 180, 0, 90, color, thickness)
    cv2.ellipse(img, (x2 - r, y1 + r), (r, r), 270, 0, 90, color, thickness)
    cv2.ellipse(img, (x1 + r, y2 - r), (r, r), 90, 0, 90, color, thickness)
    cv2.ellipse(img, (x2 - r, y2 - r), (r, r), 0, 0, 90, color, thickness)


def draw_pill_label(
    frame,
    x: int,
    y_top: int,
    text: str,
    color: Tuple[int, int, int],
    font: int,
    scale: float = 0.55,
) -> None:
    (tw, th), _ = cv2.getTextSize(text, font, scale, 1)
    pad_x, pad_y = 8, 6

    x1 = x
    y1 = max(0, y_top)
    x2 = x1 + tw + pad_x * 2
    y2 = y1 + th + pad_y * 2

    overlay = frame.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), color, -1)
    cv2.addWeighted(overlay, 0.78, frame, 0.22, 0, frame)

    cv2.putText(
        frame,
        text,
        (x1 + pad_x, y1 + th + pad_y - 2),
        font,
        scale,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )


def overlay_hud(frame, cfg: Config, damaged: int, undamaged: int, pending: int, fps_display: float) -> None:
    total = damaged + undamaged
    panel_w, panel_h = 320, 175
    x0, y0 = 18, 18

    overlay = frame.copy()
    cv2.rectangle(overlay, (x0, y0), (x0 + panel_w, y0 + panel_h), cfg.color_overlay, -1)
    cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)

    cv2.putText(frame, f"FPS {fps_display:.1f}", (x0 + 10, y0 + 28), cfg.font, 0.52, (130, 130, 130), 1, cv2.LINE_AA)

    rows = [
        (f"DAMAGED     {damaged:>4}", cfg.color_damaged),
        (f"UNDAMAGED   {undamaged:>4}", cfg.color_ok),
        (f"PENDING     {pending:>4}", cfg.color_pending),
        (f"TOTAL       {total:>4}", (220, 220, 220)), 
    ]
    y = y0 + 62
    for text, color in rows:
        cv2.putText(frame, text, (x0 + 10, y), cfg.font, 0.62, color, 1, cv2.LINE_AA)
        y += 35


def normalize_cls_name(name: str) -> str:
    return name.strip().lower().replace("-", "_").replace(" ", "_")


def map_to_label(name: str) -> Optional[Label]:
    n = normalize_cls_name(name)
    if "damaged" in n and "undamaged" not in n:
        return "damaged"
    if "undamaged" in n or n == "ok" or "good" in n:
        return "undamaged"
    return None


def safe_top1(cls_res) -> Optional[Tuple[int, float]]:
    probs = getattr(cls_res, "probs", None)
    if probs is None:
        return None
    top1 = getattr(probs, "top1", None)
    top1conf = getattr(probs, "top1conf", None)
    if top1 is None or top1conf is None:
        return None
    return int(top1), float(top1conf)


def run(cfg: Config) -> None:
    if not cfg.input_video.exists():
        raise FileNotFoundError(f"Input video not found: {cfg.input_video}")
    if not cfg.det_model_path.exists():
        raise FileNotFoundError(f"Detection model not found: {cfg.det_model_path}")
    if not cfg.cls_model_path.exists():
        raise FileNotFoundError(f"Classification model not found: {cfg.cls_model_path}")

    cfg.output_video.parent.mkdir(parents=True, exist_ok=True)
    cfg.output_csv.parent.mkdir(parents=True, exist_ok=True)

    det_model = YOLO(str(cfg.det_model_path))
    cls_model = YOLO(str(cfg.cls_model_path))

    cap = cv2.VideoCapture(str(cfg.input_video))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {cfg.input_video}")

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

    out = cv2.VideoWriter(str(cfg.output_video), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    if not out.isOpened():
        cap.release()
        raise RuntimeError(f"Cannot open output video writer: {cfg.output_video}")

    votes = defaultdict(lambda: {"damaged": 0.0, "undamaged": 0.0, "n": 0})
    locked_label: Dict[int, Label] = {}
    first_frame: Dict[int, int] = {}
    final_conf: Dict[int, float] = {}

    damaged_count = 0
    undamaged_count = 0
    frame_idx = 0
    t_prev = time.time()

    csv_file = None
    try:
        csv_file = open(cfg.output_csv, "w", newline="", encoding="utf-8")
        writer = csv.writer(csv_file)
        writer.writerow(["track_id", "label", "confidence", "first_frame"])

        pbar_total = total_frames if total_frames > 0 else None
        with tqdm(total=pbar_total, unit="fr", dynamic_ncols=True) as pbar:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                frame_idx += 1
                t_now = time.time()
                fps_live = 1.0 / max(t_now - t_prev, 1e-6)
                t_prev = t_now

                det_results = det_model.track(frame, persist=True, conf=cfg.det_conf, verbose=False)
                r = det_results[0]

                pending_count = 0

                if r.boxes is not None and r.boxes.id is not None:
                    boxes = r.boxes.xyxy.cpu().numpy().astype(int)
                    track_ids = r.boxes.id.cpu().numpy().astype(int)

                    for (x1, y1, x2, y2), tid in zip(boxes, track_ids):
                        if tid not in first_frame:
                            first_frame[tid] = frame_idx

                        if tid not in locked_label:
                            crop = pad_crop(frame, x1, y1, x2, y2, cfg.crop_padding)
                            if crop.size > 0:
                                cls_out = cls_model.predict(crop, verbose=False)[0]
                                top = safe_top1(cls_out)
                                if top is not None:
                                    cls_id, conf = top
                                    if conf >= cfg.cls_conf:
                                        name = str(cls_model.names.get(cls_id, cls_id))
                                        label = map_to_label(name)
                                        if label is not None:
                                            votes[tid][label] += conf
                                            votes[tid]["n"] += 1

                            n = int(votes[tid]["n"])
                            if n >= cfg.vote_frames:
                                d = float(votes[tid]["damaged"])
                                u = float(votes[tid]["undamaged"])
                                total_s = (d + u) or 1e-9
                                d_frac = d / total_s
                                u_frac = u / total_s

                                if d_frac >= cfg.lock_threshold:
                                    locked_label[tid] = "damaged"
                                    final_conf[tid] = d_frac
                                    damaged_count += 1
                                    writer.writerow([tid, "damaged", f"{d_frac:.3f}", first_frame[tid]])
                                elif u_frac >= cfg.lock_threshold:
                                    locked_label[tid] = "undamaged"
                                    final_conf[tid] = u_frac
                                    undamaged_count += 1
                                    writer.writerow([tid, "undamaged", f"{u_frac:.3f}", first_frame[tid]])

                        if tid in locked_label:
                            is_damaged = locked_label[tid] == "damaged"
                            color = cfg.color_damaged if is_damaged else cfg.color_ok
                            status = "DAMAGED" if is_damaged else "OK"
                            conf_str = f"{final_conf[tid]*100:.0f}%"
                        else:
                            color = cfg.color_pending
                            status = "SCANNING"
                            conf_str = f"{votes[tid]['n']}/{cfg.vote_frames}"
                            pending_count += 1

                        draw_rounded_rect(frame, (x1, y1), (x2, y2), color, thickness=2, radius=10)
                        label_text = f"ID:{tid}  {status}  {conf_str}"
                        draw_pill_label(frame, x1, max(0, y1 - 34), label_text, color, cfg.font)

                overlay_hud(frame, cfg, damaged_count, undamaged_count, pending_count, fps_live)
                out.write(frame)

                pbar.update(1)

    finally:
        cap.release()
        out.release()
        if csv_file is not None:
            csv_file.close()