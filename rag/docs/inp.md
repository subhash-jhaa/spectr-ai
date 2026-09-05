# Interaction to Next Paint (INP)

Interaction to Next Paint (INP) measures a page's overall responsiveness to user interactions. It tracks the latency of all discrete user interactions—such as clicks, taps, and keypresses—throughout the entire visit and reports the worst duration.

## User Experience Impact
INP measures interface fluidity and responsiveness. High INP causes input lag, unresponsiveness, and visual freezing when users attempt to navigate, click buttons, or type in forms.

## Official Threshold Ranges
- **Good**: ≤ 200 milliseconds
- **Needs Improvement**: 200 milliseconds – 500 milliseconds
- **Poor**: > 500 milliseconds

## Spectr Implementation
Spectr records INP latency values in milliseconds in the `WebVital.inp` table column and calculates the 75th percentile (P75) across user visits.
