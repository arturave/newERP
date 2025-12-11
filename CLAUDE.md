# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

NewERP is a manufacturing ERP system for laser cutting sheet metal operations. It's a Python desktop application using CustomTkinter for the GUI and Supabase (PostgreSQL + Cloud Storage) as the backend.

**Tech Stack:** Python 3.8+, CustomTkinter, Supabase, ezdxf (DXF), VTK/CadQuery (3D CAD), rectpack/shapely/pyclipper (nesting)

## Commands

```bash
# Run the application
python main.py

# Run with specific modules
python main.py --products    # Products catalog only
python main.py --customers   # Customers only
python main.py --pricing     # Pricing tables only
python main.py --debug       # Debug mode

# Install dependencies
pip install -r requirements.txt

# Run tests
python test_cost_engine.py
python test_cost_simulation.py
python test_nesting_integration.py

# Test database connection
python test_connection.py
```

## Architecture

### Layered Architecture Pattern
```
GUI Layer (CustomTkinter windows)
        ↓
Service Layer (Business logic, validation, transactions)
        ↓
Repository Layer (Database/Storage access)
        ↓
Supabase (PostgreSQL + Cloud Storage)
```

### Core Modules (`core/`)
- `supabase_client.py` - Singleton Supabase client (`get_supabase_client()`)
- `base_repository.py` - Base class for all repositories (CRUD, soft delete, optimistic locking)
- `base_service.py` - Base class for services (transactions, validation, events)
- `events.py` - Event bus for module communication (`EventBus`, `EventType`)
- `filters.py` - Query builder with filtering (`QueryParams`, `FilterOperator`)
- `audit.py` - Audit trail logging to `audit_log` table

### Domain Modules
- **products/** - Product catalog with CAD files (WORKING)
- **orders/** - Order management with cost calculation (IN DEVELOPMENT)
- **costing/** - Advanced nesting and cost allocation
- **customers/** - Customer management (NOT STARTED)
- **quotations/** - Quotes and pricing (NOT STARTED)
- **pricing/** - Pricing tables management

### Key Components

**CostEngine** (`orders/cost_engine.py`) - Unified cost calculation:
- Material, cutting, piercing, foil removal, bending costs
- Allocation models: `equal`, `area_proportional`, `weight_proportional`
- Cost variants: `A` (length-based), `B` (time-based)

**ProductService** (`products/service.py`) - Product catalog:
- CAD file storage (DXF, STEP) with automatic compression
- Thumbnail generation from CAD files
- Deterministic paths via `StoragePaths`

**FastNester** (`quotations/nesting/`) - Part nesting:
- Modes: `FAST` (3 attempts), `DEEP` (74+ attempts)
- Uses rectpack for bin packing

## Patterns & Conventions

### Creating Services
```python
# Always use factory functions
from products import create_product_service
service = create_product_service()
```

### Event Communication
```python
from core import get_event_bus, EventType
bus = get_event_bus()
bus.subscribe(EventType.ORDER_CREATED, handler_func)
bus.publish(EventType.ORDER_CREATED, {"order_id": "..."})
```

### Database Conventions
- Soft delete via `deleted_at` timestamp (never hard delete)
- Optimistic locking via `version` field
- All changes logged to `audit_log` table
- Use `Decimal` for financial calculations, not `float`

### Storage Paths
```python
from products import StoragePaths
path = StoragePaths.cad_2d(product_id, "dxf")
# → "products/{id}/cad/2d/cad_2d.dxf"
```

### Adding a New Module
1. Create directory: `module_name/{__init__.py, service.py, repository.py, models.py, gui/}`
2. Inherit from `BaseRepository` and `BaseService`
3. Use `StoragePaths` for file operations
4. Emit events via `EventBus`
5. Register in `main.py`

## Key Files

| File | Purpose |
|------|---------|
| `main.py` | Entry point with CLI args |
| `main_dashboard.py` | Main dashboard GUI |
| `config/settings.py` | Supabase, storage, GUI config |
| `orders/cost_engine.py` | All cost calculations |
| `orders/cost_models.py` | Cost dataclasses |
| `products/service.py` | Product catalog API |
| `products/paths.py` | Deterministic storage paths |

## Documentation

- `docs/ARCHITECTURE.md` - System design
- `docs/orders_cost_calculation.md` - Cost engine formulas
- `docs/cost_calculation_model.md` - Cost model reference
- `docs/NESTING_ALGORITHMS.md` - Nesting algorithm comparison

## GitHub Workflow

1. Use `gh issue view` to get issue details
2. Search codebase for relevant files
3. Implement changes following existing patterns
4. Run tests to verify
5. Create descriptive commit with `gh`
6. Push and create PR
