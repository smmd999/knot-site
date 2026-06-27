from pathlib import Path

site = Path(r'C:\Users\nhadi\Downloads\knot-site\knottest.framer.website')
files = list(site.rglob('*.html'))
for f in files:
    c = f.read_text(encoding='utf-8', errors='ignore')
    new = c.replace('../framerusercontent.com/', '/framerusercontent.com/')
    f.write_text(new, encoding='utf-8')
print(f'Fixed {len(files)} files')