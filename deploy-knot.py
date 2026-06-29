import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# ─────────────────────────────────────────────────────
# CONFIG — only change these if you move things around
REPO_DIR = Path(r"C:\Users\nhadi\Downloads\knot-site")
SITE_DIR = REPO_DIR / "knottest.framer.website"
GA_ID = "G-L1XD8L660K"
# ─────────────────────────────────────────────────────

# Files inside SITE_DIR that should never be deleted on clean
PRESERVE_IN_SITE = {"vercel.json", ".git"}

# Files in REPO_DIR root that the script should never touch
PRESERVE_IN_REPO = {"vercel.json", ".git", "deploy-knot.py",
                    "favicon-dark.png", "favicon-light.png", "og-image.png"}


def get_httrack_folder() -> Path:
    print("\n📂 Drag and drop your HTTrack export folder here, then hit Enter:")
    raw = input("  > ").strip().strip('"')
    path = Path(raw)

    if not path.exists():
        print(f"❌ Path not found: {path}")
        sys.exit(1)

    # Look for any .framer.website or .framer.app subfolder
    for item in sorted(path.iterdir()):
        if item.is_dir() and ("framer.website" in item.name or "framer.app" in item.name):
            print(f"  ✅ Found site folder: {item.name}")
            return item

    # Fallback — maybe they dragged the inner Framer folder directly
    if (path / "index.html").exists() and not (path / "hts-log.txt").exists():
        print(f"  ✅ Using folder directly: {path.name}")
        return path

    print("❌ Couldn't find a Framer site folder inside that export.")
    print("   Make sure you're dragging the folder HTTrack created, not a subfolder.")
    sys.exit(1)


def clean_site_dir():
    print("🗑  Clearing old site files...")
    if not SITE_DIR.exists():
        SITE_DIR.mkdir(parents=True)
        return
    for item in SITE_DIR.iterdir():
        if item.name not in PRESERVE_IN_SITE:
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

    # framerusercontent.com sits one level up from the Framer subfolder in HTTrack output
    fuc = source.parent / "framerusercontent.com"
    if fuc.exists():
        shutil.copytree(fuc, SITE_DIR / "framerusercontent.com", dirs_exist_ok=True)
        print("  ✅ framerusercontent.com assets copied")
    else:
        print("  ⚠️  framerusercontent.com not found — images may be missing")


def copy_assets():
    print("🖼  Copying favicons and OG image...")
    assets = ["favicon-dark.png", "favicon-light.png", "og-image.png"]
    for asset in assets:
        src = REPO_DIR / asset
        if src.exists():
            shutil.copy2(src, SITE_DIR / asset)
        else:
            print(f"  ⚠️  {asset} not found in repo root — skipping")


def remove_framer_badge(content: str) -> str:
    return re.sub(
        r'<div id="__framer-badge-container">.*?</div>\s*</div>',
        '',
        content,
        flags=re.DOTALL
    )


def inject_head_tags(content: str) -> str:
    inject = (
        '\n  <link rel="icon" href="/favicon-dark.png" media="(prefers-color-scheme: light)">'
        '\n  <link rel="icon" href="/favicon-light.png" media="(prefers-color-scheme: dark)">'
        '\n  <meta property="og:image" content="/og-image.png">'
        f'\n  <script async src="https://www.googletagmanager.com/gtag/js?id={GA_ID}"></script>'
        f'\n  <script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag("js",new Date());gtag("config","{GA_ID}");</script>'
    )
    # Strip any existing favicon / og:image tags Framer injected
    content = re.sub(r'<link[^>]*rel=["\'](?:icon|shortcut icon|apple-touch-icon)["\'][^>]*>\n?', '', content)
    content = re.sub(r'<meta[^>]*property=["\']og:image["\'][^>]*>\n?', '', content)
    content = content.replace("</head>", inject + "\n</head>", 1)
    return content


def fix_asset_paths(content: str) -> str:
    # HTTrack uses relative paths that break on the root page
    return content.replace('../framerusercontent.com/', '/framerusercontent.com/')


def process_html_files():
    html_files = list(SITE_DIR.rglob("*.html"))
    print(f"⚙️  Processing {len(html_files)} HTML files...")
    for filepath in html_files:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
        content = remove_framer_badge(content)
        content = inject_head_tags(content)
        content = fix_asset_paths(content)
        filepath.write_text(content, encoding="utf-8")
    print(f"  ✅ Done — {len(html_files)} files processed")


def git_push():
    print("🚀 Pushing to GitHub...")
    cmds = [
        (["git", "add", "."], "staging files"),
        (["git", "commit", "-m", "update site"], "committing"),
        (["git", "push"], "pushing"),
    ]
    for cmd, label in cmds:
        result = subprocess.run(cmd, cwd=REPO_DIR, capture_output=True, text=True)
        combined = result.stdout + result.stderr
        if result.returncode != 0:
            if "nothing to commit" in combined:
                print("  ℹ️  Nothing new to commit — already up to date")
                return
            print(f"  ❌ Git error while {label}:")
            print(f"     {result.stderr.strip()}")
            sys.exit(1)
    print("  ✅ Pushed — Vercel is deploying now (~30 seconds)")


def main():
    print("=" * 50)
    print("  Knot Deploy Script")
    print("=" * 50)

    if not REPO_DIR.exists():
        print(f"❌ Repo folder not found: {REPO_DIR}")
        sys.exit(1)

    source = get_httrack_folder()
    clean_site_dir()
    copy_new_export(source)
    copy_assets()
    process_html_files()
    git_push()

    print("\n🎉 All done! knotdesign.ca will be live in ~30 seconds.")
    input("\nPress Enter to close...")


if __name__ == "__main__":
    main()
