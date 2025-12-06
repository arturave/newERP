"""
Nesting Costing Module - Realistic cost estimation for laser cutting.

Main components:
- motion: Motion planning with lookahead and trapezoidal profile
- toolpath: DXF toolpath extraction and statistics
- material: Material cost allocation
- models: Data models (NestingResult, CostingSummary)
- services: Main NestingCostingService
"""

from .services.costing_service import (
    NestingCostingService,
    PricingConfig,
    JobOverrides,
    create_default_pricing
)
from .models.nesting_result import (
    NestingResult,
    NestingSheet,
    PartInstance,
    CostingSummary,
    AllocationModel,
    SheetMode,
    SourceType
)
from .motion.motion_planner import MachineProfile
from .toolpath.dxf_extractor import extract_toolpath_stats
from .config import (
    load_config,
    save_config,
    create_pricing_from_config,
    create_machine_profile_from_config
)
from .gui import (
    NestingCostingWindow,
    launch_nesting_costing_window,
    MotionDynamicsTestWindow,
    launch_motion_dynamics_test_window
)

__all__ = [
    # Services
    'NestingCostingService',
    'PricingConfig',
    'JobOverrides',
    'create_default_pricing',

    # Models
    'NestingResult',
    'NestingSheet',
    'PartInstance',
    'CostingSummary',
    'AllocationModel',
    'SheetMode',
    'SourceType',

    # Motion
    'MachineProfile',

    # Toolpath
    'extract_toolpath_stats',

    # Config
    'load_config',
    'save_config',
    'create_pricing_from_config',
    'create_machine_profile_from_config',

    # GUI
    'NestingCostingWindow',
    'launch_nesting_costing_window',
    'MotionDynamicsTestWindow',
    'launch_motion_dynamics_test_window',
]
