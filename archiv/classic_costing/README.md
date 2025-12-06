# Classic Costing Archive

Archived: 2025-12-04 17:18

## Reason for archival
Migration to new costing paradigm based on:
- Lookahead motion planning (trapezoid profile)
- Corner speed limiting
- Occupied area allocation (vs net area)
- Two-variant costing (A: PLN/m, B: PLN/h × time)

## Files archived
### pricing/
- cost_service.py
- cost_repository.py  
- utilization_cost_calculator.py

### quotations_pricing/
- cost_calculator.py
- pricing_tables.py

### dxf_utils/
- dxf_area_calculator.py
- dxf_polygon.py

## New system location
See: costing/ (new module)
