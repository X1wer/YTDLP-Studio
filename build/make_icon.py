"""Az alkalmazásikon (assets/icon.png és icon.ico) előállítása Pillow-val."""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
S = 1024  # szuperminta a sima élekhez


def render() -> Image.Image:
    base = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    grad = Image.new("RGBA", (S, S))
    top, bottom = (99, 91, 255), (168, 85, 247)
    for y in range(S):
        t = y / (S - 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)) + (255,)
        ImageDraw.Draw(grad).line([(0, y), (S, y)], fill=color)
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([40, 40, S - 40, S - 40], radius=230, fill=255)
    base.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(base)
    # lejátszás-háromszög
    d.polygon([(370, 250), (370, 650), (700, 450)], fill=(255, 255, 255, 255))
    # letöltés-sáv
    d.rounded_rectangle([300, 740, 724, 800], radius=30, fill=(255, 255, 255, 235))
    return base


def main() -> None:
    image = render()
    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)
    image.resize((512, 512), Image.LANCZOS).save(assets / "icon.png")
    sizes = [(s, s) for s in (16, 20, 24, 32, 40, 48, 64, 128, 256)]
    image.resize((256, 256), Image.LANCZOS).save(assets / "icon.ico", sizes=sizes)
    print("icon kész:", assets / "icon.ico")


if __name__ == "__main__":
    main()
