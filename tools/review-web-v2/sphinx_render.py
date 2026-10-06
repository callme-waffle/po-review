"""Build original Sphinx documents, reuse doctrees for current PO translations."""
from pathlib import Path
from io import BytesIO
import os,sys,json,hashlib,gettext,contextlib,shutil
from babel.messages.pofile import read_po
from babel.messages.mofile import write_mo
from sphinx.application import Sphinx
from sphinx.transforms.i18n import Locale
from sphinx.util.docutils import sphinx_domains
from sphinx.locale import translators
from docutils.transforms.references import ExternalTargets,InternalTargets,IndirectHyperlinks,AnonymousHyperlinks
from lxml import html,etree
from docutils import nodes
ROOT=Path(__file__).resolve().parent
RUN=ROOT.parent
BASE=Path('/opt/po-review/work')
_COMPILED=set()
_PO_CACHE={}

def metadata():return json.loads(Path(os.environ.get('REVIEW_MANIFEST',str(RUN/'review-web/public/data/index.json'))).read_text())
def groupof(d):return 'sdk-release' if d['po']=='releasenotes.po' else 'sdk-doc' if d['project']=='openstacksdk' else 'skyline-doc'
def appfor(group,log):
 docs=[d for d in metadata()['documents'] if groupof(d)==group]
 repo=BASE/docs[0]['project'];source=repo/('releasenotes/source' if group=='sdk-release' else 'doc/source')
 cache=ROOT/'build'/group;cache.mkdir(parents=True,exist_ok=True)
 mappings={d['source'].split('/source/',1)[1][:-4]:d['output'] for d in docs}
 extensions=['review_ext']+(['reno.sphinxext'] if group=='sdk-release' else ['sphinx.ext.autodoc'] if group=='sdk-doc' else [])
 overrides={'extensions':extensions,'html_theme':'alabaster','html_sidebars':{'**':[]},'html_theme_options':{},'html_static_path':[],'html_logo':None,'html_favicon':None,'html_extra_path':[],'html_show_sourcelink':False,'html_copy_source':False,'html_show_sphinx':False,'language':'en','locale_dirs':[str(cache/'locale')],'review_catalogs':mappings,'gettext_compact':True,'html_title':docs[0]['project'],'html_permalinks':False,'html_domain_indices':False,'html_use_index':False}
 os.chdir(repo)
 app=Sphinx(str(source),str(source),str(cache/'en'),str(cache/'doctrees'),'html',confoverrides=overrides,status=log,warning=log,freshenv=False)
 return app,cache,docs

def compile_catalog(d,cache):
 docname=d['source'].split('/source/',1)[1][:-4];domain=docname.split('/')[0]
 loc=cache/'locale/ko/LC_MESSAGES';loc.mkdir(parents=True,exist_ok=True)
 p=Path(d['output']);stat=p.stat();key=(str(p),stat.st_mtime_ns,stat.st_size)
 if key not in _PO_CACHE:
  raw=p.read_bytes();_PO_CACHE[key]=(read_po(BytesIO(raw)),hashlib.sha256(raw).hexdigest())
 po,digest=_PO_CACHE[key];compiled=(str(loc),domain,digest)
 if compiled not in _COMPILED:
  with (loc/(domain+'.mo')).open('wb') as f:write_mo(f,po)
  _COMPILED.add(compiled)
 return digest

def render(d,language,existing=None):
 group=groupof(d);logpath=ROOT/'build'/group/'render.log';logpath.parent.mkdir(parents=True,exist_ok=True)
 with logpath.open('a') as log:
  app,cache,docs=existing if existing else appfor(group,log);docname=d['source'].split('/source/',1)[1][:-4]
  if language=='ko':
   digest=compile_catalog(d,cache);app.config.language='ko'
   tree=app.env.get_doctree(docname)
   tree.ids={key:node for node in tree.findall(nodes.Element) for key in node.get('ids',[])}
   original_refs={}
   for node in tree.findall(nodes.reference):
    name=node.get('name') or node.get('refname')
    target=tuple((k,node[k]) for k in ['refuri','refid'] if k in node)
    if name and target:original_refs.setdefault(nodes.fully_normalize_name(name),set()).add(target)
   app.env.current_document.docname=docname
   app.env.current_document.default_domain=app.env.domains.get(app.config.primary_domain)
   gettext._translations.clear();translators.clear()
   with sphinx_domains(app.env):
    Locale(tree).apply()
    AnonymousHyperlinks(tree).apply()
    IndirectHyperlinks(tree).apply()
    ExternalTargets(tree).apply()
    InternalTargets(tree).apply()
   app.env.current_document.default_domain=None
   tree=app.env.get_and_resolve_doctree(docname,app.builder,doctree=tree)
   for node in tree.findall(nodes.reference):
    if 'refuri' in node or 'refid' in node:continue
    name=node.get('refname') or node.get('name','');targets=original_refs.get(nodes.fully_normalize_name(name),set())
    if len(targets)==1:
     target=dict(next(iter(targets)))
     if 'refid' not in target or target['refid'] in tree.ids:
      node.attributes.update(target);node.attributes.pop('refname',None)
   app.builder.outdir=cache/'ko';app.builder.outdir.mkdir(exist_ok=True)
   app.builder.prepare_writing({docname});app.builder.write_doc(docname,tree)
   path=cache/'ko'/(docname+'.html')
  else:path=cache/'en'/(docname+'.html')
  page=html.fromstring(path.read_bytes());body=page.xpath('//div[contains(concat(" ",normalize-space(@class)," ")," body ")]')[0]
  # Only static document markup enters the isolated preview frame.
  for node in list(body.iter()):
   if not isinstance(node.tag,str):continue
   if node.tag.lower() in {'script','iframe','object','embed','form','input','button','textarea','style','link','meta','base'}:
    node.drop_tree();continue
   for attr in list(node.attrib):
    value=node.attrib[attr].strip()
    if attr.lower().startswith('on') or attr.lower() in {'srcdoc','style'}:del node.attrib[attr]
    elif attr.lower() in {'href','src','action','xlink:href'}:
     if value.lower().startswith(('javascript:','vbscript:','data:')):del node.attrib[attr]
     elif attr=='src':
      from urllib.parse import urlsplit
      if not urlsplit(value).scheme:
       import posixpath
       asset=(cache/'en'/posixpath.normpath(posixpath.join(posixpath.dirname(docname),value))).resolve()
       if asset.is_relative_to((cache/'en').resolve()) and asset.is_file() and asset.suffix.lower() in {'.png','.jpg','.jpeg','.gif','.svg','.webp'}:
        import base64,mimetypes
        node.attrib[attr]='data:'+mimetypes.guess_type(str(asset))[0]+';base64,'+base64.b64encode(asset.read_bytes()).decode()
       else:node.attrib.pop(attr,None)
   classes=node.get('class','').split()
   ids=[c.removeprefix('review-entry-') for c in classes if c.startswith('review-entry-')]
   if ids:node.set('data-entry',ids[0]);node.set('tabindex','0')
  content=etree.tostring(body,encoding='unicode',method='html')
  wrapper='<!doctype html><html lang="'+('ko' if language=='ko' else 'en')+'"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/frame.css"><script defer src="/frame.js"></script></head><body data-language="'+language+'">'+content+'</body></html>'
  return wrapper

def main():
 mode=sys.argv[1]
 if mode=='build':
  group=sys.argv[2];p=ROOT/'build'/group;p.mkdir(parents=True,exist_ok=True)
  with (p/'build.log').open('w') as log:
   app,cache,docs=appfor(group,log);app.build(force_all=True)
   assert all((cache/'en'/(d['source'].split('/source/',1)[1][:-4]+'.html')).exists() for d in docs)
   print(json.dumps({'group':group,'documents':len(docs),'status':app.statuscode}))
 elif mode=='render':
  d=next(d for d in metadata()['documents'] if d['id']==sys.argv[2]);output=Path(sys.argv[4]);output.parent.mkdir(parents=True,exist_ok=True);output.write_text(render(d,sys.argv[3]));print(str(output))
if __name__=='__main__':main()
