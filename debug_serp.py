# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import serpapi, os
from dotenv import load_dotenv
load_dotenv(override=True)
from chatbot_core import _fetch_ai_overview
c = serpapi.Client(api_key=os.getenv('SERP_API_KEY'))
r = c.search({'engine':'google','q':'tahun berapa dahana berdiri','hl':'id','gl':'id','num':5})
tok = (r.get('ai_overview') or {}).get('page_token','')
print("tok len", len(tok))
txt, urls = _fetch_ai_overview('tahun berapa dahana berdiri', tok)
print("txt:", txt[:1000])
print("urls:", urls)
