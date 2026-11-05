"""Accessibility check renderings for every figure PDF.

figures/check/<name>_gray.png         greyscale (luminance) at 300 dpi
figures/check/<name>_deuteranopia.png deuteranopia simulation (colorspacious, severity 100)
figures/<name>_gray.png               copy of the greyscale check next to the PDF (plan, Section 7)
These files are then inspected by eye; this script only produces them and
reports the smallest luminance difference between the engines' two colours.
"""
from pathlib import Path

import pymupdf as fitz
import numpy as np
from colorspacious import cspace_convert
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "figures"
CHK = FIG / "check"


def render(pdf: Path, dpi=300) -> np.ndarray:
    doc = fitz.open(pdf)
    pix = doc[0].get_pixmap(dpi=dpi, alpha=False)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)


def luminance(hex_colour: str) -> float:
    rgb = np.array([int(hex_colour[i:i + 2], 16) for i in (1, 3, 5)]) / 255
    return float(np.dot(rgb, [0.299, 0.587, 0.114]))


def main():
    CHK.mkdir(parents=True, exist_ok=True)
    for pdf in sorted(FIG.glob("F*.pdf")):
        img = render(pdf)
        gray = Image.fromarray(img).convert("L")
        gray.save(CHK / f"{pdf.stem}_gray.png")
        gray.save(FIG / f"{pdf.stem}_gray.png")
        deut = cspace_convert(img / 255.0, {"name": "sRGB1+CVD", "cvd_type": "deuteranomaly", "severity": 100}, "sRGB1")
        Image.fromarray((np.clip(deut, 0, 1) * 255).astype(np.uint8)).save(CHK / f"{pdf.stem}_deuteranopia.png")
        print("checked", pdf.name, img.shape[1], "x", img.shape[0], "px")
    print("luminance ClickHouse orange", round(luminance("#E69F00"), 3), "DuckDB blue", round(luminance("#0072B2"), 3))


if __name__ == "__main__":
    main()
