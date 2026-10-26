"""Render assets/*.svg to PNG with headless Edge/Chrome (maintainer helper, Windows).

python test/render_assets.py            # regenerates assets/logo.png and assets/infographic.png
python test/render_assets.py --preview  # 1x renders into test/_out/ only
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "test" / "_out"
ASSETS = {"logo": (520, 600), "infographic": (1600, 960)}
BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "msedge",
    "chrome",
    "chromium",
]


def find_browser() -> str:
    for candidate in BROWSERS:
        if Path(candidate).is_file() or shutil.which(candidate):
            return candidate
    sys.exit("No Edge/Chrome found for rendering.")


def render(browser: str, name: str, width: int, height: int, scale: float, target: Path) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    svg = ROOT / "assets" / f"{name}.svg"
    html = OUT / f"render_{name}.html"
    html.write_text(
        "<!doctype html><html><head><style>html,body{margin:0;background:transparent;overflow:hidden}"
        f"img{{display:block;width:{width}px;height:{height}px}}</style></head>"
        f"<body><img src='{svg.as_uri()}'></body></html>",
        encoding="utf-8",
    )
    subprocess.run(
        [
            browser,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            f"--user-data-dir={OUT / 'browser-profile'}",
            f"--force-device-scale-factor={scale}",
            "--default-background-color=00000000",
            f"--window-size={width},{height}",
            f"--screenshot={target}",
            html.as_uri(),
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    print(f"{target.relative_to(ROOT)} ({target.stat().st_size} bytes)")


def main() -> None:
    preview = "--preview" in sys.argv
    browser = find_browser()
    for name, (width, height) in ASSETS.items():
        target = OUT / f"{name}_preview.png" if preview else ROOT / "assets" / f"{name}.png"
        render(browser, name, width, height, 1 if preview else 2, target)


if __name__ == "__main__":
    main()
