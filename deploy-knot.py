import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# ─────────────────────────────────────────────────────
# CONFIG
REPO_DIR = Path(r"C:\Users\nhadi\Downloads\knot-site")
SITE_DIR = REPO_DIR / "knottest.framer.website"
GITHUB_URL = "https://github.com/smmd999/knot-site.git"

# These files live in the repo root and should never be overwritten
PRESERVE = ["vercel.json", ".git", "deploy-knot.py", "favicon-dark.png", "favicon-light.png", "og-image.png"]
# ─────────────────────────────────────────────────────

def get_httrack_folder():
    print("\n📂 Drag and drop your new HTTrack export folder here, then hit Enter:")
    raw = input("  > ").strip().strip('"')
    path = Path(raw)

    # Look for any .framer.website or .framer.app subfolder
    for item in path.iterdir():
        if item.is_dir() and ("framer.website" in item.name or "framer.app" in item.name):
            print(f"  ✅ Found site folder: {item.name}")
            return item

    # Fallback — if they dragged the site folder itself
    if (path / "index.html").exists() and not (path / "hts-log.txt").exists():
        return path

    print("❌ Couldn't find a Framer site folder inside that export. Try again.")
    sys.exit(1)

def clean_site_dir():
    print("🗑  Clearing old site files...")
    for item in SITE_DIR.iterdir():
        if item.name not in PRESERVE:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

def copy_new_export(source: Path):
    print("📋 Copying new export...")
    for item in source.iterdir():
        dest = SITE_DIR / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)
    # Copy framerusercontent.com from parent HTTrack folder into site
    fuc = source.parent / "framerusercontent.com"
    if fuc.exists():
        shutil.copytree(fuc, SITE_DIR / "framerusercontent.com", dirs_exist_ok=True)
        print("  ✅ framerusercontent.com assets copied")
    else:
        print("  ⚠️  framerusercontent.com folder not found in HTTrack export")

def copy_assets():
    print("🖼  Copying favicons and OG image...")
    assets = ["favicon-dark.png", "favicon-light.png", "og-image.png"]
    for asset in assets:
        src = REPO_DIR / asset
        if src.exists():
            shutil.copy2(src, SITE_DIR / asset)
        else:
            print(f"  ⚠️  Warning: {asset} not found in repo root — skipping")

def remove_framer_badge(content: str) -> str:
    content = re.sub(
        r'<div id="__framer-badge-container">.*?</div>\s*</div>',
        '',
        content,
        flags=re.DOTALL
    )
    return content

def inject_head_tags(content: str) -> str:
    inject = (
    '\n  <link rel="icon" href="/favicon-dark.png" media="(prefers-color-scheme: light)">'
    '\n  <link rel="icon" href="/favicon-light.png" media="(prefers-color-scheme: dark)">'
    '\n  <meta property="og:image" content="/og-image.png">'
    '\n  <script async src="https://www.googletagmanager.com/gtag/js?id=G-L1XD8L660K"></script>'
    '\n  <script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag("js",new Date());gtag("config","G-L1XD8L660K");</script>'
)
    # Remove any existing favicon / og:image tags Framer may have added
    content = re.sub(r'<link[^>]*rel=["\'](?:icon|shortcut icon|apple-touch-icon)["\'][^>]*>\n?', '', content)
    content = re.sub(r'<meta[^>]*property=["\']og:image["\'][^>]*>\n?', '', content)
    content = content.replace("</head>", inject + "\n</head>", 1)
    return content

def process_html_files():
    html_files = list(SITE_DIR.rglob("*.html"))
    print(f"⚙️  Processing {len(html_files)} HTML files...")
    for filepath in html_files:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
        content = remove_framer_badge(content)
        content = inject_head_tags(content)
        filepath.write_text(content, encoding="utf-8")
    print(f"  ✅ Done — {len(html_files)} files updated")

def git_push():
    print("🚀 Pushing to GitHub...")
    cmds = [
        ["git", "add", "."],
        ["git", "commit", "-m", "update site"],
        ["git", "push"],
    ]
    for cmd in cmds:
        result = subprocess.run(cmd, cwd=REPO_DIR, capture_output=True, text=True)
        if result.returncode != 0 and "nothing to commit" not in result.stdout:
            print(f"  ❌ Git error: {result.stderr}")
            sys.exit(1)
    print("  ✅ Pushed — Vercel is deploying now")

def main():
    print("=" * 50)
    print("  Knot Site Deploy Script")
    print("=" * 50)

    if not SITE_DIR.exists():
        print(f"❌ Repo site folder not found: {SITE_DIR}")
        sys.exit(1)

    source = get_httrack_folder()
    clean_site_dir()
    copy_new_export(source)
    copy_assets()
    process_html_files()
    git_push()

    print("\n🎉 All done! Vercel will be live in ~30 seconds.")
    input("\nPress Enter to close...")

if __name__ == "__main__":
    main()
