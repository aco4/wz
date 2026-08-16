import base64, os
B = os.path.dirname(os.path.abspath(__file__))
html = open(f'{B}/template.html').read()
b64 = lambda p: base64.b64encode(open(p, 'rb').read()).decode()
for tag, f in [('UBC','Ubuntu-C'),('LATO','Lato-Regular'),('LATOB','Lato-Bold'),('UMONO','UbuntuMono-R')]:
    html = html.replace('{{%s}}' % tag, b64(f'{B}/fonts/{f}.woff2'))
html = html.replace('{{DATA}}', open(f'{B}/techdata.json').read())
out = os.path.join(B, os.pardir, 'index.html')
open(out, 'w').write(html)
print(out, round(os.path.getsize(out)/1024, 1), 'KB')
