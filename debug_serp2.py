# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from chatbot_core import search_serp_and_extract
for i in range(3):
    print(f"===== TRY {i+1} =====")
    text, urls = search_serp_and_extract('tahun berapa dahana berdiri')
    print(text[:1200])
    print("URLS:", urls)
    print()
