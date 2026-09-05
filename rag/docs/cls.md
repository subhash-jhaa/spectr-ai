# Cumulative Layout Shift (CLS)

Cumulative Layout Shift (CLS) measures the visual stability of a webpage. It calculates unexpected layout movements that occur while content dynamically loads without user interaction.

## User Experience Impact
CLS measures unexpected visual movement. High CLS causes accidental clicks, text jumpiness, and user disorientation when buttons, images, or ads shift location unexpectedly during reading or clicking.

## Official Threshold Ranges
- **Good**: ≤ 0.1
- **Needs Improvement**: 0.1 – 0.25
- **Poor**: > 0.25

## Spectr Implementation
Spectr stores CLS fractional shift scores in the `WebVital.cls` table column and presents the 75th percentile (P75) layout shift score per URL or project.
