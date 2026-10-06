"""Serve only the dedicated review export, with no directory listing or writes."""
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit,unquote
import re
ROOT=Path(__file__).resolve().parent/'public'
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(ROOT),**kwargs)
    def allowed(self):
        path=unquote(urlsplit(self.path).path)
        return path in ('/','/index.html','/app.js','/style.css','/data/index.json','/translation-review-checklist.xlsx') or re.fullmatch(r'/data/[0-9a-f]{20}\.json',path)
    def do_GET(self):
        if not self.allowed():self.send_error(404);return
        super().do_GET()
    def do_HEAD(self):
        if not self.allowed():self.send_error(404);return
        super().do_HEAD()
    def end_headers(self):
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.send_header('Cache-Control','no-cache')
        super().end_headers()
    def list_directory(self,path):self.send_error(404);return None
if __name__=='__main__':
    ThreadingHTTPServer(('127.0.0.1',8080),Handler).serve_forever()
