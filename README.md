# STATS19 Intelligence Platform

UK road casualty intelligence app using [STATS19](https://data.gov.uk/dataset/cb7ae6f0-4be6-4935-9277-47e5ce24a11f/road-safety-data) open data.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Data

STATS19 data is included in the repo under `datasets/` (UK Gov open data). The app works out of the box after cloning.

### Faster loading (optional)

Run once to convert CSV to Parquet and prebuild views:

```bash
python scripts/prepare_data.py
```

Subsequent app starts will load from Parquet (3–10× faster) and skip view computation.

## Deploy to Streamlit Cloud

1. Push this repo to GitHub.
2. In [Streamlit Cloud](https://share.streamlit.io), create a new app from the repo.
3. **Critical**: In app settings → **Build command**, set:
   ```
   python scripts/prepare_data.py
   ```
   This prebuilds the Parquet cache during deploy. Without it, the app loads CSVs on first request and can hit memory limits or time out (EOF health check failure).
4. Main file: `app.py`. Deploy.

## Pages

- Executive Overview — metrics, charts, operational alerts
- GeoRisk Map — map view by severity
- Risk Factors — hazard profiles, trunk roads
- Vehicle Intelligence — make/model, manoeuvre analysis
- Casualty Intelligence — priority queue, pedestrian analysis
- Data Quality & Refresh Status
