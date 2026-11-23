# WellCast: Backend API Contract & Frontend UI/UX Specification

This document defines the exact JSON contracts served by AWS Lambda + API Gateway (**Phase 5**), the S3 precomputed static JSON structure (**Phase 4**), and the 7-step React + Leaflet frontend architecture, mobile UX, and EN/HI/MR localization specification (**Phase 6**).

---

## 1. Backend Serving Architecture & Caching Strategy

To deliver fast responses (<200 ms) at virtually \$0 runtime cost, `backend/lambda_handler.py` reads precomputed JSON objects from `s3://<DATA_BUCKET>/api/` rather than running live Athena queries on every user click.

### S3 Key-to-Endpoint Mapping
| Endpoint | S3 Object Key Read by Lambda | Lambda Memory Cache TTL |
|---|---|---|
| `GET /health` | `api/meta.json` (lightweight liveness + version metadata) | 60s |
| `GET /blocks` | `api/blocks.json` (filtered in-memory by `state`, `district`, `risk_class`) | 300s |
| `GET /blocks/{block_id}/forecast` | `api/forecasts/{scenario}/{block_id}.json` | 300s |
| `GET /blocks/{block_id}/history` | `api/history/{block_id}.json` | 300s |
| `GET /rankings` | `api/rankings/{state}.json` (sliced by `limit`, filtered by `scenario` / `district`) | 300s |

> **Optional Boundary Serving:** Either bundle simplified `MH_blocks.geojson` (<1.5 MB) in `frontend/public/geo/` (zero API latency, served directly via CloudFront CDN) OR expose `GET /geojson?state=MH` reading `api/geojson/MH_blocks.geojson`. **Recommended:** Serve GeoJSON statically via CloudFront (`frontend/public/geo/`) for fastest map paint and zero Lambda payload overhead.

---

## 2. REST API Endpoint Contracts

**Base URL:** `https://<api-id>.execute-api.ap-south-1.amazonaws.com/prod`  
**Standard Headers on All Responses:**
```http
Content-Type: application/json; charset=utf-8
Access-Control-Allow-Origin: https://<your-cloudfront-id>.cloudfront.net
Access-Control-Allow-Methods: GET, OPTIONS
Access-Control-Allow-Headers: Content-Type
Cache-Control: public, max-age=300
```

### 2.1 `GET /health`
Verifies Lambda liveness, S3 connectivity, and active forecast generation metadata.

- **200 OK Response:**
```json
{
  "status": "ok",
  "service": "wellcast-api",
  "region": "ap-south-1",
  "model_version": "xgb-v1-sagemaker-20261126",
  "forecast_season": "2027-pre-monsoon",
  "blocks_indexed": 358,
  "generated_at": "2026-11-27T04:15:00Z"
}
```

### 2.2 `GET /blocks`
Lists blocks with current risk class and coordinates for the selector dropdown and map overlay.

- **Query Parameters:**
  - `state` (optional, e.g., `MH` or `Maharashtra`)
  - `district` (optional, case-insensitive substring or exact match)
  - `scenario` (optional, default `normal`; allowed: `normal`, `minus10`, `minus20`, `minus30`)
- **200 OK Response:**
```json
{
  "state": "Maharashtra",
  "granularity": "block",
  "scenario": "normal",
  "forecast_season": "2027-pre-monsoon",
  "count": 358,
  "blocks": [
    {
      "block_id": "MH-PUN-012",
      "state": "Maharashtra",
      "district": "Pune",
      "block_name": "Baramati",
      "lat": 18.1517,
      "lon": 74.5777,
      "extraction_stage": "Semi-Critical",
      "current_depth_mbgl": 12.8,
      "predicted_depth_mbgl": 14.2,
      "risk_class": "Watch",
      "risk_score": 61.4
    }
  ]
}
```

### 2.3 `GET /blocks/{block_id}/forecast`
Returns detailed forecast, P10/P90 confidence range, risk class, model attribution, and plain-language advice for a specific block and rainfall scenario.

- **Path Parameter:** `block_id` (alphanumeric + hyphens only, regex `^[A-Z]{2}-[A-Z0-9]{3}-[0-9]{3}$`)
- **Query Parameter:** `scenario` (default `normal`; allowed: `normal`, `minus10`, `minus20`, `minus30`)
- **200 OK Response:**
```json
{
  "block_id": "MH-PUN-012",
  "state": "Maharashtra",
  "district": "Pune",
  "block_name": "Baramati",
  "granularity": "block",
  "scenario": "normal",
  "rainfall_pct_of_normal": 100,
  "forecast_season": "2027-pre-monsoon",
  "current_obs_date": "2026-11-01",
  "current_depth_mbgl": 12.8,
  "predicted_depth_mbgl": 14.2,
  "lower_bound": 12.9,
  "upper_bound": 15.6,
  "predicted_yoy_change_mbgl": 1.1,
  "extraction_stage": "Semi-Critical",
  "risk_class": "Watch",
  "risk_score": 61.4,
  "well_count": 14,
  "is_imputed_history": false,
  "rainfall_source_level": "district_mapped",
  "advice": {
    "en": "Water levels show moderate decline. Prefer low-water crops (millets, pulses), adopt drip irrigation, and avoid drilling deeper borewells without local survey.",
    "hi": "भूजल स्तर में मध्यम गिरावट के संकेत हैं। कम पानी वाली फसलें (बाजरा, दालें) चुनें, ड्रिप सिंचाई अपनाएं और बिना जांच के नया गहरा बोरवेल न खुदवाएं।",
    "mr": "भूजल पातळीत मध्यम घट होण्याची शक्यता आहे. कमी पाण्याची पिके (बाजरी, कडधान्ये) निवडा, ठिबक सिंचन वापरा आणि तज्ज्ञांच्या सल्ल्याशिवाय खोल बोअरवेल खोदू नका."
  },
  "available_scenarios": ["normal", "minus10", "minus20", "minus30"]
}
```
- **400 Bad Request** (invalid `scenario` or malformed `block_id`):
  `{"error": "Invalid scenario. Allowed values: normal, minus10, minus20, minus30"}`
- **404 Not Found** (unknown `block_id`):
  `{"error": "Block not found", "block_id": "MH-XXX-999"}`

### 2.4 `GET /blocks/{block_id}/history`
Returns multi-year historical groundwater depths and seasonal/monthly rainfall for plotting historical context alongside the forecast.

- **200 OK Response:**
```json
{
  "block_id": "MH-PUN-012",
  "block_name": "Baramati",
  "district": "Pune",
  "water_levels": [
    {
      "obs_date": "2022-05-01",
      "season": "pre-monsoon",
      "depth_mbgl": 11.4,
      "well_count": 12,
      "is_imputed": false
    },
    {
      "obs_date": "2022-11-01",
      "season": "post-monsoon",
      "depth_mbgl": 8.9,
      "well_count": 13,
      "is_imputed": false
    }
  ],
  "rainfall_seasonal": [
    {
      "period": "2022-monsoon",
      "rainfall_mm": 512.4,
      "normal_mm": 540.0,
      "departure_pct": -5.1
    }
  ]
}
```

### 2.5 `GET /rankings`
Returns the Planner View ranked list of highest-risk blocks sorted descending by `risk_score`.

- **Query Parameters:**
  - `state` (default `MH`)
  - `district` (optional filter)
  - `scenario` (default `normal`)
  - `limit` (integer `1`–`500`, default `20`)
- **200 OK Response:**
```json
{
  "state": "Maharashtra",
  "scenario": "normal",
  "forecast_season": "2027-pre-monsoon",
  "summary": {
    "total_blocks": 358,
    "critical": 48,
    "watch": 124,
    "safe": 162,
    "insufficient_data": 24
  },
  "rankings": [
    {
      "rank": 1,
      "block_id": "MH-BEE-004",
      "district": "Beed",
      "block_name": "Georai",
      "extraction_stage": "Over-Exploited",
      "current_depth_mbgl": 19.6,
      "predicted_depth_mbgl": 22.1,
      "lower_bound": 20.4,
      "upper_bound": 23.8,
      "predicted_yoy_change_mbgl": 2.3,
      "risk_class": "Critical",
      "risk_score": 91.2
    }
  ]
}
```

---

## 3. Frontend Architecture & Component Hierarchy

**Stack:** React 18 + Vite + Leaflet (`react-leaflet` or native `leaflet`) + Recharts (for forecast + shaded `Area` confidence band) + Vanilla CSS / Tailwind CSS.

```text
frontend/
├── index.html
├── package.json
├── .env.example                 # VITE_API_BASE_URL=https://<api-id>.execute-api.ap-south-1.amazonaws.com/prod
├── public/
│   └── geo/
│       └── MH_blocks.geojson    # Simplified block boundaries (<1.5 MB)
└── src/
    ├── main.jsx
    ├── App.jsx                  # Top-level tabs: Farmer View | Planner View + Language Toggle
    ├── api/
    │   └── wellcastApi.js       # Fetch wrapper with timeout, abort controller & clean error parsing
    ├── i18n/
    │   ├── index.js             # Lightweight useTranslation() hook
    │   ├── en.json              # English UI labels + risk advice
    │   ├── hi.json              # Hindi UI labels + risk advice
    │   └── mr.json              # Marathi UI labels + risk advice
    ├── components/
    │   ├── HeaderBar.jsx        # Brand, View Switcher (Farmer / Planner), Language Toggle (EN/HI/MR)
    │   ├── BlockSelector.jsx    # District -> Block searchable dropdowns
    │   ├── MapView.jsx          # Interactive Leaflet choropleth / marker map + Risk Legend
    │   ├── RiskBadge.jsx        # Accessible high-contrast pill (Safe / Watch / Critical / Insufficient Data)
    │   ├── ForecastChart.jsx    # Historical line + Predicted point + Shaded P10-P90 Confidence Band (inverted Y-axis!)
    │   ├── ScenarioSlider.jsx   # 4-stop slider: 100% Normal, -10%, -20%, -30% Rainfall
    │   ├── AdvicePanel.jsx      # Plain-language seasonal recommendations + data quality / well_count badge
    │   ├── PlannerView.jsx      # Summary KPI cards, District filter, Ranked At-Risk Table, CSV Export
    │   ├── DataLimitationsModal.jsx  # Always-visible attribution & honest limitations link/drawer
    │   └── ErrorState.jsx       # Offline API / Missing Data / Loading Skeleton states
    └── styles/
        └── global.css           # Mobile-first responsive grid & high-contrast color tokens
```

---

## 4. Incremental 7-Step Frontend Build Order (Phase 6)

Build strictly in this order so there is a working, demoable product at every single checkpoint:

1. **Step 1 — Block Selector + Live Risk Badge (`T6.1`):** Connect `wellcastApi.js` to `/blocks` and `/blocks/{id}/forecast`. Render district/block dropdowns and display Risk Badge + Predicted Depth (`mbgl`) + Confidence Range text.
2. **Step 2 — Interactive Leaflet Map (`T6.2`):** Render `MH_blocks.geojson` polygons (or centroid markers fallback) colored by `risk_class`. Clicking a block highlights its border and syncs with the detail panel. Include a clear map legend.
3. **Step 3 — Historical + Forecast Chart (`T6.3`):** Fetch `/blocks/{id}/history` and render a time-series chart with:
   - **Inverted Y-axis** (`0 m` ground surface at the top, deeper depths going downward) so farmers intuitively see water dropping down or rising up!
   - Solid historical line, dashed forecast segment, and semi-transparent shaded confidence band (`lower_bound` to `upper_bound`).
4. **Step 4 — Rainfall Scenario Slider (`T6.4`):** 4 discrete stops (`100% Normal`, `90% (-10%)`, `80% (-20%)`, `70% (-30%)`). Changing the slider fetches `/blocks/{id}/forecast?scenario=<key>` (cached client-side in a `Map` after first load so sliding back and forth is 0 ms!). Also updates map risk styling if viewing scenario mode.
5. **Step 5 — Advice Panel & EN/HI/MR Language Toggle (`T6.5`):** Display localized crop/irrigation/drilling advice, monitoring well count, CGWB official extraction stage badge, and imputed-data indicator (if `is_imputed_history: true`).
6. **Step 6 — Mobile-First Layout Audit (`T6.6`):** Verify clean stacking on `375 x 812` mobile viewports (search bar at top -> collapsible map -> risk card -> slider -> chart -> advice), minimum 44 px touch targets, zero horizontal scroll.
7. **Step 7 — Planner View (`T6.6`):** Tab switch to Planner Dashboard calling `/rankings?state=MH&limit=100`: summary counts (Critical / Watch / Safe), scenario switcher, district filter, sortable table, click row to inspect block on map, and one-click "Download CSV" for district planners.

---

## 5. Accessible Color Palette & Visual Hierarchy

Use high-contrast WCAG AA-compliant colors plus text labels + icons (never rely on color alone):

| State | Primary Hex | Soft Background | Text Hex | Icon / Indicator |
|---|---|---|---|---|
| **Safe** | `#15803D` | `#DCFCE7` | `#14532D` | Shield / Checkmark |
| **Watch** | `#B45309` | `#FEF3C7` | `#78350F` | Alert Triangle |
| **Critical** | `#B91C1C` | `#FEE2E2` | `#7F1D1D` | Warning Octagon |
| **Insufficient Data** | `#4B5563` | `#F3F4F6` | `#1F2937` | Info / Dash |
| **Water / Primary Accent** | `#0369A1` | `#E0F2FE` | `#0C4A6E` | Droplet |

---

## 6. Pre-Drafted Plain-Language Advice Strings (EN / HI / MR)

Ready to drop into `ml/make_forecasts.py` and `frontend/src/i18n/`:

| Risk Class | English (`en`) | Hindi (`hi`) | Marathi (`mr`) |
|---|---|---|---|
| **Safe** | Groundwater levels look stable for the coming season. Continue balanced irrigation and maintain farm ponds or recharge pits to preserve reserves. | आगामी मौसम के लिए भूजल स्तर स्थिर दिख रहा है। संतुलित सिंचाई जारी रखें और जल भंडार बनाए रखने के लिए खेत तालाब या रिचार्ज गड्ढों की देखभाल करें। | आगामी हंगामासाठी भूजल पातळी स्थिर दिसत आहे. संतुलित सिंचन सुरू ठेवा आणि पाणी साठा टिकवण्यासाठी शेततळे किंवा पुनर्भरण खड्ड्यांची निगा राखा. |
| **Watch** | Water levels show moderate stress. Prefer low-water crops (millets, pulses), use drip or sprinkler irrigation, and avoid drilling deeper borewells without checking local recharge. | भूजल स्तर पर मध्यम दबाव के संकेत हैं। कम पानी वाली फसलें (बाजरा, दालें) चुनें, ड्रिप या स्प्रिंकलर सिंचाई अपनाएं और बिना स्थानीय जांच के गहरा बोरवेल न खुदवाएं। | भूजल पातळीवर मध्यम ताण जाणवत आहे. कमी पाण्याची पिके (बाजरी, कडधान्ये) निवडा, ठिबक किंवा तुषार सिंचन वापरा आणि तज्ज्ञांच्या सल्ल्याशिवाय खोल बोअरवेल खोदू नका. |
| **Critical** | High depletion risk predicted next season. Avoid water-intensive crops (like sugarcane or summer paddy), prioritize drinking water conservation, and consult local water planners for recharge or tanker support. | अगले मौसम में भूजल की भारी कमी का जोखिम है। अधिक पानी वाली फसलों (जैसे गन्ना या ग्रीष्मकालीन धान) से बचें, पेयजल संरक्षण को प्राथमिकता दें और जल विभाग से सहायता के लिए संपर्क करें। | पुढील हंगामात भूजल पातळीत तीव्र घटीचा धोका आहे. जास्त पाण्याची पिके (जसे ऊस किंवा उन्हाळी भात) टाळा, पिण्याच्या पाण्याचे संवर्धन करा आणि स्थानिक जल नियोजकांशी संपर्क साधा. |
| **Insufficient Data** | Monitoring well data for this block is too limited to produce a reliable forecast. Check nearby blocks or official CGWB/GSDA advisories before major irrigation decisions. | इस ब्लॉक के लिए विश्वसनीय पूर्वानुमान बनाने हेतु पर्याप्त निगरानी कुओं का डेटा उपलब्ध नहीं है। सिंचाई के बड़े निर्णयों से पहले नजदीकी ब्लॉक या आधिकारिक सलाह देखें। | या तालुक्यासाठी विश्वसनीय अंदाज तयार करण्यासाठी पुरेसा निरीक्षण विहिरींचा डेटा उपलब्ध नाही. सिंचनाचे मोठे निर्णय घेण्यापूर्वी जवळच्या तालुक्याची माहिती किंवा शासकीय सल्ला घ्या. |

---

## 7. CloudFront + Private S3 SPA Deployment Spec (`T6.7`)

1. Create private S3 bucket `wellcast-web-<account-id>-ap-south-1` with **Block all public access = ON**.
2. Create CloudFront distribution:
   - **Origin:** `wellcast-web-<account-id>-ap-south-1.s3.ap-south-1.amazonaws.com`
   - **Origin access:** Origin Access Control (OAC) — copy the generated S3 bucket policy onto `wellcast-web-*`.
   - **Viewer Protocol Policy:** `Redirect HTTP to HTTPS`.
   - **Default Root Object:** `index.html`.
   - **Custom Error Responses (for React SPA client routing):**
     - HTTP `403` -> Customize Error Response -> Response Page Path: `/index.html`, HTTP Response Code: `200`.
     - HTTP `404` -> Customize Error Response -> Response Page Path: `/index.html`, HTTP Response Code: `200`.
3. Copy the resulting `https://<dist-id>.cloudfront.net` URL into:
   - API Gateway CORS `AllowOrigins` (replacing `*`)
   - `README.md` top table
   - `Docs/build-summary.md` & Google Drive `LINKS.txt`
