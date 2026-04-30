import os
from instruction_search.sheets import SheetsWorkbook
from instruction_search.sync import POSTS_MAX_SHEET

wb = SheetsWorkbook(os.environ["BOT_ANALYTICS_SPREADSHEET_ID"], os.environ["GOOGLE_SERVICE_ACCOUNT_FILE"])
rows = wb.read_rows(POSTS_MAX_SHEET)
print("rows_total=", len(rows))
if not rows:
    raise SystemExit(0)
headers = rows[0]
idx_text = headers.index("text_raw") if "text_raw" in headers else -1
idx_title = headers.index("title_raw") if "title_raw" in headers else -1
idx_url = headers.index("post_url") if "post_url" in headers else -1
idx_id = headers.index("source_post_id") if "source_post_id" in headers else -1

hits = []
for r in rows[1:]:
    txt = (r[idx_text] if idx_text >= 0 and idx_text < len(r) else "") or ""
    low = txt.lower()
    if ("badd" in low) or ("????" in low) or ("????" in low):
        hits.append((
            r[idx_id] if idx_id >= 0 and idx_id < len(r) else "",
            r[idx_title] if idx_title >= 0 and idx_title < len(r) else "",
            r[idx_url] if idx_url >= 0 and idx_url < len(r) else "",
            txt[:120].replace("\n", " ")
        ))

print("badd_hits=", len(hits))
for h in hits[:10]:
    print(h)
