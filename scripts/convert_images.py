from pathlib import Path
from PIL import Image

source_dir = Path("assets/images")
output_dir = Path("assets/images-jpg")
output_dir.mkdir(parents=True, exist_ok=True)

for png_path in source_dir.glob("*.png"):
    output_path = output_dir / f"{png_path.stem}.jpg"

    with Image.open(png_path) as img:
        rgb = img.convert("RGB")
        rgb.save(output_path, "JPEG", quality=90, optimize=True)

    print(f"Converted {png_path} -> {output_path}")