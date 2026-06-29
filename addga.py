from pathlib import Path

GA_SNIPPET = (
    '<script async src="https://www.googletagmanager.com/gtag/js?id=G-L1XD8L660K"></script>\n'
    '<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag("js",new Date());gtag("config","G-L1XD8L660K");</script>'
)

site = Path(r'C:\Users\nhadi\Downloads\knot-site\knottest.framer.website')
files = list(site.rglob('*.html'))
for f in files:
    c = f.read_text(encoding='utf-8', errors='ignore')
    if 'G-L1XD8L660K' not in c:
        c = c.replace('</head>', GA_SNIPPET + '\n</head>', 1)
        f.write_text(c, encoding='utf-8')
print(f'Done - {len(files)} files')