from pathlib import Path

from PIL import Image

SOURCE = Path("/home/ubuntu/family-ai-github/50_开发_dev/apps/web/public/bangyang-reference/home-screen-ui-crop.png")
TARGET = Path("/home/ubuntu/family-ai-mobile/assets/images/ui01")


def crop(image: Image.Image, box: tuple[int, int, int, int], name: str) -> None:
    image.crop(box).save(TARGET / name)


def main() -> None:
    TARGET.mkdir(parents=True, exist_ok=True)
    image = Image.open(SOURCE).convert("RGB")

    # Coordinates are taken directly from the 610 × 1102 original UI-01 reference.
    crop(image, (23, 211, 581, 379), "assessment-banner.png")
    crop(image, (24, 847, 208, 998), "recommendation-live.png")
    crop(image, (217, 847, 400, 998), "recommendation-course.png")
    crop(image, (410, 847, 591, 998), "recommendation-case.png")


if __name__ == "__main__":
    main()
