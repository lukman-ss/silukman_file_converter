from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--images", nargs="+", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--lang", default="en")
    parser.add_argument("--health-check", action="store_true")
    args = parser.parse_args()

    from paddleocr import PaddleOCR

    ocr = PaddleOCR(lang=args.lang)
    pages = []

    for index, image_path in enumerate(args.images, start=1):
        result = ocr.predict(str(image_path))
        texts = []
        scores = []
        boxes = []

        for item in result or []:
            rec_texts = item.get("rec_texts", []) if hasattr(item, "get") else []
            rec_scores = item.get("rec_scores", []) if hasattr(item, "get") else []
            rec_boxes = item.get("rec_boxes", []) if hasattr(item, "get") else []
            texts.extend(str(text) for text in rec_texts if str(text).strip())
            scores.extend(float(score) for score in rec_scores)
            try:
                boxes.extend(rec_boxes.tolist())
            except AttributeError:
                boxes.extend(rec_boxes)

        pages.append(
            {
                "page": index,
                "image": str(image_path),
                "text": "\n".join(texts),
                "confidence": mean(scores) if scores else 0,
                "boxes": boxes,
            }
        )

    all_scores = [page["confidence"] for page in pages if page["confidence"]]
    output = {
        "success": any(page["text"] for page in pages),
        "engine": "paddleocr-external",
        "text": "\n\n".join(page["text"] for page in pages if page["text"]),
        "confidence": mean(all_scores) if all_scores else 0,
        "pages": pages,
        "error": None if any(page["text"] for page in pages) else "No text detected",
        "health_check": bool(args.health_check),
    }

    Path(args.output).write_text(json.dumps(output, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
