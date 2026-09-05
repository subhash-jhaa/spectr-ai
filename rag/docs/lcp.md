# Largest Contentful Paint (LCP)

Largest Contentful Paint (LCP) measures the time it takes for the largest visual element on a page to fully render. This element is typically a hero image, video frame, or main body text block. LCP marks the point when the main content of the page has likely loaded.

## User Experience Impact
LCP measures perceived load speed. A fast LCP reassures users that the page is useful and functioning, reducing bounce rates and frustration caused by slow-loading visual content.

## Official Threshold Ranges
- **Good**: ≤ 2.5 seconds
- **Needs Improvement**: 2.5 seconds – 4.0 seconds
- **Poor**: > 4.0 seconds

## Spectr Implementation
Spectr collects raw LCP values in seconds via the `WebVital.lcp` table column and displays the P75 value for selected date ranges.
