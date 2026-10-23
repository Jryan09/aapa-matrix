# AAPA Matrix 1C Analysis System

Web app (Python + Streamlit). Departments submit their outputs; the system analyzes them and produces
**Matrix 1C** (Results | Performance Indicators | Target | Actual Accomplishment | Issues/Concerns/Gaps |
Recommendation/Intervention) in the official layout, taken from `template_1c.xlsx`.

## Run on your computer
    pip install -r requirements.txt
    streamlit run app.py

## Put it on the web (free): Streamlit Community Cloud
1. Upload this folder to a GitHub repository.
2. Go to share.streamlit.io, sign in with GitHub, click **New app**, choose the repo and `app.py`.
3. (Optional) In **Settings > Secrets** add:
       ADMIN_PASSWORD = "choose-a-password"
       ANTHROPIC_API_KEY = "sk-ant-..."
   - With ADMIN_PASSWORD, departments can still submit data, but only the admin office can view,
     edit and export the analysis.
   - With ANTHROPIC_API_KEY, a button appears to polish the wording with Claude.
4. You get a public link to share with all departments.

Important: free hosting resets its disk when the app restarts or sleeps, so `aapa.db` can be lost.
For permanent storage, host on Render/Railway with a persistent disk (set env var AAPA_DB to the disk path),
or ask me to switch the storage to Supabase/PostgreSQL.

## How the analysis works
- Quantitative: % accomplished = Actual / Target (numbers, percentages, or words like "completed", "ongoing").
  Rating: 100%+ Fully, 80-99 Substantially, 50-79 Partially, below 50 Not accomplished / Critical.
- Qualitative: the department's remarks are coded into themes (funding, manpower, equipment, delays/procurement,
  weather, coordination, technology, policy, capacity, community) using English and Filipino keywords
  in `analysis.py` (edit `THEMES` to add your own words).
- Each theme has a standard recommendation; the Issues and Recommendation cells are drafted from these
  and can be edited on screen before exporting.

## Files
app.py (web interface) - analysis.py (rules) - db.py (SQLite) - ingest.py (readers) - matrix1c.py (Excel export)
