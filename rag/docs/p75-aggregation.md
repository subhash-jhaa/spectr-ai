# P75 (75th Percentile) Aggregation

P75 represents the 75th percentile score of a performance dataset, meaning 75% of user visits experienced performance equal to or better than this value. Core Web Vitals standardizes on P75 instead of arithmetic averages.

## User Experience Impact
P75 reflects the overwhelming majority of real user experiences. Averages are easily skewed by extreme outliers, high-speed corporate connections, or isolated slow device spikes, masking actual user performance issues.

## Official Threshold Ranges
- **Metric Type**: Statistical aggregation standard (evaluates whether the 75th percentile of visits meets Good thresholds).

## Spectr Implementation
Spectr aggregates `WebVital` metrics by sorting values ascendingly and selecting the score at the 75th percentile for each page URL and project dashboard.
