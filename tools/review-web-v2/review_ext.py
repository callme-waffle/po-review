from pathlib import Path
from babel.messages.pofile import read_po
from sphinx.transforms import SphinxTransform
from sphinx.util.nodes import extract_messages
from docutils import nodes
class MarkMessages(SphinxTransform):
 default_priority=19
 def apply(self):
  app=self.app;doc=self.env.current_document.docname
  catalog=app.config.review_catalogs.get(doc)
  if not catalog:return
  cache=getattr(app,'_review_catalog_cache',{})
  if catalog not in cache:
   with open(catalog,'rb') as stream: po=read_po(stream)
   cache[catalog]={m.id:i for i,m in enumerate(po) if m.id and isinstance(m.id,str)}
   app._review_catalog_cache=cache
  mapping=cache[catalog]
  for node,msg in extract_messages(self.document):
   index=mapping.get(msg)
   if index and isinstance(node,nodes.Element):node['classes'].append('review-entry-'+str(index))
def setup(app):
 app.add_config_value('review_catalogs',{},'env')
 app.add_transform(MarkMessages)
 return {'version':'1','parallel_read_safe':True}
