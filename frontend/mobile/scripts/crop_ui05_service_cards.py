from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "research" / "baselines" / "ui35-original" / "delivery-community-reference-458x1128.png"
TARGET = ROOT / "assets" / "images" / "ui05-service-cards-baseline.png"


def main() -> None:
    image = Image.open(SOURCE)
    # 原图坐标：四张陪跑服务卡，不含顶部标题与本周完成度卡。
    cropped = image.crop((23, 126, 435, 337))
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    cropped.save(TARGET, "PNG", optimize=True)


if __name__ == "__main__":
    main()
