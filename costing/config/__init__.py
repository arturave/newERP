"""Configuration management for costing module."""

import json
from pathlib import Path
from typing import Dict, Any

from ..services.costing_service import PricingConfig, MachineProfile

CONFIG_DIR = Path(__file__).parent
DEFAULT_CONFIG_PATH = CONFIG_DIR / "default_config.json"


def load_config(config_path: str = None) -> Dict[str, Any]:
    """
    Load configuration from JSON file.

    Args:
        config_path: Path to config file (default: default_config.json)

    Returns:
        Configuration dictionary
    """
    if config_path is None:
        config_path = DEFAULT_CONFIG_PATH
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_config(config: Dict[str, Any], config_path: str = None):
    """
    Save configuration to JSON file.

    Args:
        config: Configuration dictionary
        config_path: Path to save config (default: default_config.json)
    """
    if config_path is None:
        config_path = DEFAULT_CONFIG_PATH
    else:
        config_path = Path(config_path)

    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4)


def create_pricing_from_config(config: Dict[str, Any] = None) -> PricingConfig:
    """
    Create PricingConfig from configuration dictionary.

    Args:
        config: Configuration dict (loads default if None)

    Returns:
        PricingConfig instance
    """
    if config is None:
        config = load_config()

    pricing = PricingConfig()

    # Material prices
    if 'material_prices_pln_per_kg' in config:
        pricing.material_prices_per_kg = config['material_prices_pln_per_kg']

    # Cutting prices
    if 'cutting_prices_pln_per_m' in config:
        pricing.cutting_prices = config['cutting_prices_pln_per_m']

    # Cutting speeds
    if 'cutting_speeds_m_min' in config:
        pricing.cutting_speeds = config['cutting_speeds_m_min']

    # Pierce times
    if 'pierce_times_s' in config:
        pricing.pierce_times = config['pierce_times_s']

    # Pierce costs
    if 'pierce_costs_pln' in config:
        pricing.pierce_costs = config['pierce_costs_pln']

    # Foil removal
    if 'foil_removal' in config:
        foil = config['foil_removal']
        pricing.foil_removal_speed_m_min = foil.get('speed_m_min', 15.0)
        pricing.foil_cost_per_m2 = foil.get('cost_per_m2', 2.0)

    # Machine rate
    pricing.machine_rate_pln_per_h = config.get('machine_rate_pln_per_h', 300.0)

    # Operational cost
    pricing.operational_cost_per_sheet = config.get('operational_cost_per_sheet_pln', 40.0)

    return pricing


def create_machine_profile_from_config(config: Dict[str, Any] = None) -> MachineProfile:
    """
    Create MachineProfile from configuration dictionary.

    Args:
        config: Configuration dict (loads default if None)

    Returns:
        MachineProfile instance
    """
    if config is None:
        config = load_config()

    machine_config = config.get('machine_profile', {})

    return MachineProfile(
        max_accel_mm_s2=machine_config.get('max_accel_mm_s2', 2000.0),
        max_rapid_mm_s=machine_config.get('max_rapid_mm_s', 500.0),
        square_corner_velocity_mm_s=machine_config.get('square_corner_velocity_mm_s', 50.0),
        junction_deviation_mm=machine_config.get('junction_deviation_mm', 0.05),
        use_junction_deviation=machine_config.get('use_junction_deviation', False)
    )


__all__ = [
    'load_config',
    'save_config',
    'create_pricing_from_config',
    'create_machine_profile_from_config',
    'DEFAULT_CONFIG_PATH'
]
