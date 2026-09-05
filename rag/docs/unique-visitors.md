# Unique Visitors vs. Total Page Views

Unique visitors represents the count of distinct individual users visiting a website during a specific time period. Total page views measures the cumulative number of times any page on the site was loaded or reloaded.

## User Experience Impact
Distinguishing unique visitors from page views separates actual audience reach from overall consumption intensity. A high page-view-to-unique-visitor ratio reflects deep user engagement and multi-page exploration.

## Official Threshold Ranges
- **Metric Type**: Audience volume and engagement ratio (no static Good/Poor cutoffs apply).

## Spectr Implementation
Spectr computes unique visitors by counting distinct user IP addresses and session IDs in the `Event` table, while total page views counts total `Event` records.
