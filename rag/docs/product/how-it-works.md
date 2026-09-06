# How Spectr Works

Spectr operates via a lightweight tracking script embedded into website client pages:

1. **Script Installation**: A lightweight `<script>` tag is included in the `<head>` of the user's website with a unique project `data-site-id`.
2. **Event & Vital Collection**: As visitors navigate pages, the client script sends non-blocking beacons containing page URLs, referrers, and Core Web Vitals (LCP, INP, CLS) to Spectr ingestion APIs.
3. **Data Anonymization**: Spectr hashes incoming IP addresses and session IDs without storing personal identifying information (PII) or third-party cookies.
4. **Dashboard Aggregation**: Aggregated stats and P75 Core Web Vitals are processed and displayed in real time on the user's dashboard and queryable via Ask Spectr.
