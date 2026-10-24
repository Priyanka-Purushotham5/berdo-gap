# Structure

```
app.py                     Streamlit UI (pages: Building, City view, About & sources)
berdo/
  load.py                  download + cache + normalize the disclosure sheet
  limits.py                limits table, property-type mapping, blended limit
  exposure.py              excess tons and ACP by period
  scenarios.py             heat pumps, efficiency, green power
  memo.py                  Claude memo call + templated fallback
data/
  berdo_limits.csv
  property_type_map.csv
  golden_buildings.csv
  cache/                   gitignored
tests/
  test_exposure_properties.py
  test_scenarios_properties.py
  test_limits_properties.py
  test_golden.py
.streamlit/secrets.toml    gitignored
```
