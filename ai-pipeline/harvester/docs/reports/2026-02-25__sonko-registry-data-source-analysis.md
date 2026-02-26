# SONKO Registry Data Source Analysis

**Date**: 2026-02-25  
**Scope**: Analysis of SONKO registry data sources  
**Primary Target**: https://data.economy.gov.ru/analytics/sonko  
**Status**: Technical access issues encountered - server timeout

---

## Executive Summary

The SONKO (Socially Oriented Non-Commercial Organizations) registry is maintained by the Ministry of Economic Development of the Russian Federation. The data is published as open data on the government's data portal at data.economy.gov.ru/analytics/sonko.

**Current Status**: Direct access to the portal was unsuccessful due to server timeouts. This may indicate high server load, rate limiting, network restrictions, or temporary unavailability.

---

## 1. Data Source Identification

### 1.1 Primary Source
**URL**: https://data.economy.gov.ru/analytics/sonko  
**Maintained by**: Ministry of Economic Development of the Russian Federation  
**Type**: Open data portal  
**Update Frequency**: Monthly

### 1.2 Alternative Source - Federal Tax Service Registry
**URL**: https://rmsp-pp.nalog.ru/search.html?m=SubjectExt&t=0  
**Description**: Unified Registry of Small and Medium-Sized Businesses
- Includes SONKO organizations
- Provides search functionality
- Export to Excel available
- Last known update: 15.01.2026

---

## 2. Known Data Characteristics

### 2.1 Registry Scope
The SONKO registry includes organizations (from 1 January 2017) that are:
- Recipients of subsidies
- Recipients of grants
- Providers of social services
- Performers of socially beneficial services

### 2.2 Data Formats
- **CSV** - Primary format for open data
- **XLSX** - Excel format (available through FTS portal)
- **XLS** - Legacy Excel format

### 2.3 Update Schedule
- **Frequency**: Monthly
- **Last Known Update**: January 2026

---

## 3. Expected Data Fields

Based on similar SONKO registries:

### Organization Identification
- INN (Tax Identification Number)
- OGRN (State Registration Number)
- Organization Name
- Full Legal Name

### SONKO Status
- SONKO Status
- Date of Registry Inclusion
- Date of Exclusion (if applicable)
- Grounds for Inclusion

### Support Information
- Types of Support Received
- Subsidies
- Grants
- Support Period

### Contact & Location
- Address
- Region
- Contact Information

### Activity Information
- Activity Directions
- Types of Social Services
- Economic Activity Codes

---

## 4. Technical Challenges Encountered

### 4.1 Server Access Issues
Multiple connection attempts to data.economy.gov.ru resulted in timeouts.

**Possible Causes**:
1. Geographic restrictions (portal may restrict access from outside Russia)
2. Rate limiting
3. DDoS protection
4. Server load
5. Authentication requirements

---

## 5. Recommended Access Strategies

### 5.1 Immediate Short-Term Solution
Use Federal Tax Service Portal:
1. Navigate to https://rmsp-pp.nalog.ru/search.html?m=SubjectExt&t=0
2. Apply filter: Organization Type = SONKO
3. Export results using Excel download button
4. Process XLSX file

### 5.2 Medium-Term Solution
Implement browser automation with:
- Russian IP address or VPN
- User-Agent spoofing
- Cookie management
- Retry logic with exponential backoff

### 5.3 Long-Term Solution
Contact Ministry of Economic Development:
- Request API access credentials
- Inquire about bulk data dumps
- Establish automated update pipeline

---

## 6. Integration with Navigator Project

### 6.1 Use Cases
1. **Organization Validation**: Verify organization INN against SONKO registry
2. **Data Enrichment**: Add SONKO status field to organizations
3. **Discovery**: Identify new organizations not yet in Navigator database

### 6.2 Database Schema Extension
Add SONKO fields to organizations table:
- sonko_status
- sonko_inclusion_date
- sonko_support_types
- sonko_last_verified_at

### 6.3 Enrichment Pipeline
1. Download SONKO Registry (monthly)
2. Parse & Validate Data
3. Match with Navigator Organizations by INN
4. Update Navigator Database
5. Create Audit Trail

---

## 7. Next Steps

### Immediate Actions
1. Test FTS portal access
2. Download sample SONKO data
3. Setup VPN for data.economy.gov.ru access

### Short-Term
1. Implement browser automation
2. Build parser for SONKO CSV/XLSX
3. Design database schema additions
4. Create INN-based matching algorithm

### Medium-Term
1. Schedule automated monthly updates
2. Build enrichment pipeline
3. Contact Ministry for official API access
4. Implement data quality monitoring

---

## 8. Related Resources

### Official Sources
- Ministry of Economic Development: https://economy.gov.ru/
- Open Data Portal: https://data.gov.ru/
- Federal Tax Service: https://nalog.gov.ru/

### Alternative Data Sources
- Unified State Register: https://egrul.nalog.ru/
- Presidential Grants Fund XLSX (see previous report)
- Regional SONKO registries

---

## Conclusion

### Summary
- SONKO registry exists and is maintained by Ministry of Economic Development
- Data is published monthly as open data
- Alternative access confirmed via Federal Tax Service portal
- Direct access failed due to technical issues
- Manual intervention required to establish reliable data pipeline

### Recommended Approach
1. **Immediate**: Use FTS portal as temporary data source
2. **Parallel**: Investigate data.economy.gov.ru access (VPN, browser automation)
3. **Long-term**: Establish direct API partnership with Ministry

### Risk Assessment
- **Data Availability**: LOW RISK - Multiple sources available
- **Access Difficulty**: MEDIUM RISK - Technical challenges present
- **Data Quality**: MEDIUM RISK - Expect normalization needs
- **Update Reliability**: LOW RISK - Government commitment to monthly updates
- **Integration Complexity**: LOW RISK - INN-based matching straightforward

---

**Report Status**: INCOMPLETE - Technical barriers prevent full analysis  
**Next Review**: After implementing browser automation solution
