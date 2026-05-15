from pathlib import Path

from inspection_core import Config, run

DET_MODEL_PATH = r"D:\YOLO_Project\best1.pt"
CLS_MODEL_PATH = r"D:\YOLO_Project\best.pt"


def main() -> None:
    video_path = input("Enter video path: ").strip().strip('"')
    if not video_path:
        raise SystemExit("No video path provided.")

    cfg = Config(
        det_model_path=Path(DET_MODEL_PATH),
        cls_model_path=Path(CLS_MODEL_PATH),
        input_video=Path(video_path),
        output_video=Path("final_output.mp4"),
        output_csv=Path("inspection_report.csv"),
        show_window=True,  # window for local script
    )
    run(cfg)


if __name__ == "__main__":
    main()