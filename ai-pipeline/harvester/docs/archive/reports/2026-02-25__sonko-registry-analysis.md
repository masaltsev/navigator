# SONKO Registry Data Source Analysis

**Date**: 2026-02-25
**Primary Target**: https://data.economy.gov.ru/analytics/sonko
**Status**: Technical access issues - server timeout

## Executive Summary

The SONKO registry is maintained by the Ministry of Economic Development. Direct access failed due to timeouts.

## Data Sources

### Primary Source
- URL: https://data.economy.gov.ru/analytics/sonko
- Maintained by: Ministry of Economic Development
- Update Frequency: Monthly
- Format: CSV, XLSX

### Alternative Source  
- URL: https://rmsp-pp.nalog.ru/search.html?m=SubjectExt&t=0
- Description: Federal Tax Service Registry
- Status: Confirmed working (Jan 2026)
- Export: Excel download available

## Technical Issues

Connection attempts resulted in timeouts. Possible causes:
- Geographic restrictions
- Rate limiting
- DDoS protection
- Authentication requirements

## Recommended Approach

1. Use FTS portal as immediate data source
2. Implement browser automation with VPN
3. Contact Ministry for API access

## Next Steps

- Test FTS portal download
- Setup VPN for data.economy.gov.ru
- Build SONKO data parser
- Design database schema integration
