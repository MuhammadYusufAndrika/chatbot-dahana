# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from chatbot_core import ask, search_serp_and_extract
text, urls = search_serp_and_extract('tahun berapa dahana berdiri')
print("=== SEARCH URLS ===")
for u in urls:
    print("-", u)
print()
r = ask('tahun berapa dahana berdiri')
print("intent:", r.get('intent'), "| source:", r.get('source'))
print("=== ANSWER ===")
print(r.get('answer'))
print()
print("=== RETURNED URLS ===")
for u in r.get('urls', []):
    print("-", u)
