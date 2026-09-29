# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import serpapi, os
from dotenv import load_dotenv
load_dotenv(override=True)
c = serpapi.Client(api_key=os.getenv('SERP_API_KEY'))
for loc in [None, "Indonesia"]:
    params = {'engine':'google','q':'tahun berapa dahana berdiri','hl':'id','gl':'id','num':5}
    if loc:
        params['location'] = loc
    print("=== location =", loc, "===")
    r = c.search(params)
    tok = (r.get('ai_overview') or {}).get('page_token','')
    print("tok len", len(tok))
    try:
        r2 = c.search({'engine':'google_ai_overview','page_token':tok})
        aio = dict((r2.get('ai_overview') or {}))
        print("blocks:", str(aio.get('text_blocks'))[:500])
        print("refs:", str(aio.get('references'))[:300])
    except Exception as e:
        print("ERR:", e)
    print()
