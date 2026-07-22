import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# ─────────────────────────────────────────────────────
# CONFIG — only change these if you move things around
REPO_DIR = Path(r"C:\Users\nhadi\Downloads\knot-site")
SITE_DIR = REPO_DIR / "knottest.framer.website"
GA_ID = "G-L1XD8L660K"
SITE_DOMAIN = "https://knotdesign.ca"
# ─────────────────────────────────────────────────────

PRESERVE_IN_SITE = {"vercel.json", ".git"}

# HTTrack embeds the real URL path in a comment, e.g.
# <!-- Mirrored from spicy-step-903793.framer.app/changelog/knot-ai-3.0 by HTTrack ... -->
# even when it saves the file as knot-ai-3.html (strips .0 as a fake extension).
MIRRORED_FROM_RE = re.compile(
    r"<!-- Mirrored from [^/\s]+/(\S+?) by HTTrack",
    re.IGNORECASE,
)


def get_httrack_folder() -> Path:
    print("\n📂 Drag and drop your HTTrack export folder here, then hit Enter:")
    raw = input("  > ").strip().strip('"')
    path = Path(raw)

    if not path.exists():
        print(f"❌ Path not found: {path}")
        sys.exit(1)

    for item in sorted(path.iterdir()):
        if item.is_dir() and ("framer.website" in item.name or "framer.app" in item.name):
            print(f"  ✅ Found site folder: {item.name}")
            return item

    if (path / "index.html").exists() and not (path / "hts-log.txt").exists():
        print(f"  ✅ Using folder directly: {path.name}")
        return path

    print("❌ Couldn't find a Framer site folder inside that export.")
    print("   Drag the folder HTTrack created, not a subfolder.")
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

    fuc = source.parent / "framerusercontent.com"
    if fuc.exists():
        shutil.copytree(fuc, SITE_DIR / "framerusercontent.com", dirs_exist_ok=True)
        print("  ✅ framerusercontent.com assets copied")
    else:
        print("  ⚠️  framerusercontent.com not found — images may be missing")


def copy_assets():
    print("🖼  Copying favicons and OG image...")
    for asset in ["favicon-dark.png", "favicon-light.png", "og-image.png"]:
        src = REPO_DIR / asset
        if src.exists():
            shutil.copy2(src, SITE_DIR / asset)
        else:
            print(f"  ⚠️  {asset} not found in repo root — skipping")


def fix_truncated_filenames():
    """
    HTTrack treats trailing .0 / .1 / etc as file extensions and strips them
    from saved filenames (knot-ai-3.0 → knot-ai-3.html). The real slug is
    still in the 'Mirrored from' HTML comment — use that to rename, and
    rewrite any href/src that still points at the truncated name.
    """
    print("🔧 Fixing truncated filenames...")
    renames: list[tuple[Path, Path]] = []

    for filepath in SITE_DIR.rglob("*.html"):
        head = filepath.read_text(encoding="utf-8", errors="ignore")[:4000]
        match = MIRRORED_FROM_RE.search(head)
        if not match:
            continue

        real_slug = match.group(1).rstrip("/")  # e.g. changelog/knot-ai-3.0
        expected = SITE_DIR / f"{real_slug}.html"
        if filepath.resolve() == expected.resolve():
            continue
        if filepath.parent != expected.parent:
            rel = filepath.relative_to(SITE_DIR)
            print(f"  ⚠️  Skipping {rel} — Mirrored path folder doesn't match on-disk folder")
            continue
        renames.append((filepath, expected))

    if not renames:
        print("  ✅ No truncated filenames found")
        return

    link_rewrites: list[tuple[str, str]] = []
    for src, dest in renames:
        rel_src = src.relative_to(SITE_DIR).as_posix()
        rel_dest = dest.relative_to(SITE_DIR).as_posix()
        if dest.exists():
            print(f"  ⚠️  Target already exists ({rel_dest}) — skipping {rel_src}")
            continue
        src.rename(dest)
        print(f"  ✅ Renamed {rel_src} → {rel_dest}")
        link_rewrites.append((src.name, dest.name))

    if not link_rewrites:
        return

    # HTTrack also rewrites in-page links to the truncated filename
    fixed_files = 0
    for filepath in SITE_DIR.rglob("*.html"):
        content = filepath.read_text(encoding="utf-8", errors="ignore")
        updated = content
        for old_name, new_name in link_rewrites:
            updated = updated.replace(old_name, new_name)
        if updated != content:
            filepath.write_text(updated, encoding="utf-8")
            fixed_files += 1
    if fixed_files:
        print(f"  ✅ Rewrote truncated links in {fixed_files} HTML files")


def fetch_404_page(framer_host: str):
    """
    HTTrack refuses to save Framer's /404 page because Framer correctly returns
    HTTP 404 with the custom HTML body. Download it ourselves (keeping the body
    even on 404) so Vercel can serve it as 404.html.
    """
    print("📥 Fetching custom 404 page from Framer...")
    url = f"https://{framer_host}/404"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; KnotDeploy/1.0)"})
    try:
        with urlopen(req, timeout=60) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except HTTPError as e:
        # Framer intentionally returns status 404 with the designed page body
        if e.code == 404:
            html = e.read().decode("utf-8", errors="ignore")
        else:
            print(f"  ❌ Failed to fetch 404 page: HTTP {e.code}")
            sys.exit(1)
    except URLError as e:
        print(f"  ❌ Failed to fetch 404 page: {e.reason}")
        sys.exit(1)

    if len(html) < 1000:
        print("  ❌ 404 response looked empty — aborting so we don't push a broken page")
        sys.exit(1)

    dest = SITE_DIR / "404.html"
    dest.write_text(html, encoding="utf-8")
    print(f"  ✅ Saved 404.html ({len(html):,} bytes) from {url}")


def remove_framer_badge(content: str) -> str:
    """
    Remove the Made in Framer badge by deleting the entire balanced
    #__framer-badge-container tree.

    A naive non-greedy regex only matches through the first nested
    </div></div> pair, which leaves the rest of the badge DOM behind
    (especially on curl'd pages like 404.html). Walk div depth instead.
    """
    marker = '<div id="__framer-badge-container">'
    start = content.find(marker)
    if start == -1:
        return content

    j = start
    depth = 0
    while j < len(content):
        if content.startswith("</div>", j):
            depth -= 1
            j += 6
            if depth == 0:
                end = j
                while end < len(content) and content[end] in " \t\r\n":
                    end += 1
                return content[:start] + content[end:]
            continue
        # Count real <div ...> opens (not </div>)
        if content.startswith("<div", j):
            nxt = content[j + 4 : j + 5]
            if nxt in (" ", ">", "\n", "\t", "\r"):
                depth += 1
                j += 4
                continue
        j += 1

    # Unbalanced markup — leave content unchanged rather than corrupt the page
    return content


def inject_head_tags(content: str) -> str:
    inject = (
        '\n  <link rel="icon" href="/favicon-dark.png" media="(prefers-color-scheme: light)">'
        '\n  <link rel="icon" href="/favicon-light.png" media="(prefers-color-scheme: dark)">'
        '\n  <meta property="og:image" content="/og-image.png">'
        f'\n  <script async src="https://www.googletagmanager.com/gtag/js?id={GA_ID}"></script>'
        f'\n  <script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag("js",new Date());gtag("config","{GA_ID}");</script>'
        # Framer's own client-side JS re-renders <img> tags after the page loads
        # (this happens on a hard refresh specifically), and re-adds a broken
        # srcset/sizes list even after we've stripped it from the static HTML.
        # This watcher keeps stripping it back off every time Framer's JS
        # tries to re-add it, so images always stay at full quality.
        '\n  <script>'
        '(function(){'
        'function stripBadAttrs(img){'
        'if(img.hasAttribute("srcset")){img.removeAttribute("srcset");}'
        'if(img.hasAttribute("sizes")){img.removeAttribute("sizes");}'
        '}'
        'document.querySelectorAll("img").forEach(stripBadAttrs);'
        'var mo=new MutationObserver(function(mutations){'
        'mutations.forEach(function(m){'
        'if(m.type==="attributes"&&(m.attributeName==="srcset"||m.attributeName==="sizes")&&m.target.tagName==="IMG"){'
        'stripBadAttrs(m.target);'
        '}'
        'if(m.type==="childList"){'
        'm.addedNodes.forEach(function(n){'
        'if(n.nodeType===1){'
        'if(n.tagName==="IMG"){stripBadAttrs(n);}'
        'n.querySelectorAll&&n.querySelectorAll("img").forEach(stripBadAttrs);'
        '}'
        '});'
        '}'
        '});'
        '});'
        'mo.observe(document.documentElement,{subtree:true,childList:true,attributes:true,attributeFilter:["srcset","sizes"]});'
        '})();'
        '</script>'
    )
    content = re.sub(r'<link[^>]*rel=["\'](?:icon|shortcut icon|apple-touch-icon)["\'][^>]*>\n?', '', content)
    content = re.sub(r'<meta[^>]*property=["\']og:image["\'][^>]*>\n?', '', content)
    content = content.replace("</head>", inject + "\n</head>", 1)
    return content


def fix_asset_paths(content: str, relative_path: Path) -> str:
    # Fix framerusercontent relative paths at any depth
    content = re.sub(r'(\.\./)+framerusercontent\.com/', '/framerusercontent.com/', content)

    # Fix relative paths to JS/CSS/font assets so deep pages load correctly on hard refresh
    content = re.sub(
        r'((?:src|href)=")(\.\./)+([^"]*\.(?:js|mjs|css|woff2?|ttf|eot)(?:[?#][^"]*)?)"',
        r'\1/\3"',
        content
    )

    # Canonical must match the real route. Use the on-disk path (after truncation
    # renames) — HTTrack also truncates relative canonical hrefs (e.g. writes
    # knot-ai-3.html inside a page that should be /changelog/knot-ai-3.0).
    disk_path = relative_path.as_posix()
    content = re.sub(
        r'<link rel="canonical" href="[^"]*"',
        f'<link rel="canonical" href="{SITE_DOMAIN}/{disk_path}"',
        content,
        count=1,
    )

    # Rewrite og:url from framer.app domain to knotdesign.ca
    content = re.sub(
        r'<meta property="og:url" content="https://[^/]+/([^"]*)"',
        rf'<meta property="og:url" content="{SITE_DOMAIN}/\1"',
        content
    )

    return content


def strip_broken_srcset(content: str) -> str:
    """
    HTTrack sometimes saves the different quality-size versions of an image
    under mismatched filenames (e.g. one ends in ...80703.png, the full-size
    one ends in ...888ac.png — same picture, different broken filenames), and
    also mangles the &amp; separators inside the srcset list (writes them as
    &amp;amp; instead of &amp;). Browsers can't reliably parse a broken list
    like that and silently fall back to the smallest/blurriest image option.

    Fix: remove the "sizes" and "srcset" attributes entirely from every image,
    so each image just loads its single full-quality "src" every time.
    This trades away picking a smaller image for tiny screens, which doesn't
    matter for a small site's gallery images, in exchange for guaranteed
    full quality with zero ambiguity.
    """
    content = re.sub(r'\s+sizes="[^"]*"', '', content)
    content = re.sub(r'\s+srcset="[^"]*"', '', content)
    return content


def process_html_files():
    html_files = list(SITE_DIR.rglob("*.html"))
    print(f"⚙️  Processing {len(html_files)} HTML files...")
    for filepath in html_files:
        relative_path = filepath.relative_to(SITE_DIR)
        content = filepath.read_text(encoding="utf-8", errors="ignore")
        content = remove_framer_badge(content)
        content = inject_head_tags(content)
        content = fix_asset_paths(content, relative_path)
        content = strip_broken_srcset(content)
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
    fix_truncated_filenames()
    # Must run after clean/copy (those wipe the site folder) and before
    # process_html_files so 404.html gets badge/favicon/GA/path fixes too.
    fetch_404_page(source.name)
    process_html_files()
    git_push()

    print("\n🎉 All done! knotdesign.ca will be live in ~30 seconds.")
    input("\nPress Enter to close...")


if __name__ == "__main__":
    main()
