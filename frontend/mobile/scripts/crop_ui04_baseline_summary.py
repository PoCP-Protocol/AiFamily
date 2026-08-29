from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "research" / "baselines" / "ui35-original" / "growth-plan-90day-reference-434x1130.png"
TARGET = ROOT / "assets" / "images" / "ui04-plan-summary-baseline.png"


def main() -> None:
    image = Image.open(SOURCE)
    # 原图坐标：暖橙方案摘要 + 3/12/36/90 统计，不含顶部系统栏与后续时间线。
    cropped = image.crop((17, 143, 417, 365))
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    cropped.save(TARGET, "PNG", optimize=True)


if __name__ == "__main__":
    main()
