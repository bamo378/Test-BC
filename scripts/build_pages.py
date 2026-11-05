"""Build a static Pages site from an explicit public asset list, never private data."""
import argparse
from pathlib import Path
from shutil import copytree
ROOT=Path(__file__).resolve().parents[1]
def index_html():
    text=(ROOT/'polyimmo/static/index.html').read_text()
    text=text.replace('<html lang="fr">','<html lang="fr" data-hosting="github-pages">')
    text=text.replace('/static/','./polyimmo/static/')
    return text.replace('</head>','<link rel="stylesheet" href="./polyimmo/static/pages.css"></head>')
def build(output):
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    (out/'index.html').write_text(index_html());(out/'.nojekyll').touch()
    public=out/'polyimmo/static'; public.mkdir(parents=True,exist_ok=True)
    for file in (ROOT/'polyimmo/static').rglob('*'):
        if file.is_symlink():raise ValueError('Symbolic links are not allowed in public assets')
        if file.is_file() and (file.suffix in ('.js','.css','.svg') or file.name in ('logo-polyimmo.png','fflate-LICENSE.txt')):
            dest=public/file.relative_to(ROOT/'polyimmo/static');dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(file.read_bytes())
    (out/'data').mkdir(exist_ok=True)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',default='_site');parser.add_argument('--root-index',action='store_true');args=parser.parse_args()
    if args.root_index:(ROOT/'index.html').write_text(index_html());(ROOT/'.nojekyll').touch()
    else:build(args.out)
