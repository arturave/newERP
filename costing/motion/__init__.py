"""Motion planning module for realistic cutting time estimation."""

from .motion_planner import (
    MachineProfile,
    MotionSegment,
    corner_speed_limit,
    plan_speeds,
    segment_time_trapezoid,
    effective_vmax,
    estimate_motion_time,
    estimate_simple_time,
    m_min_to_mm_s,
    mm_s_to_m_min
)

__all__ = [
    'MachineProfile',
    'MotionSegment',
    'corner_speed_limit',
    'plan_speeds',
    'segment_time_trapezoid',
    'effective_vmax',
    'estimate_motion_time',
    'estimate_simple_time',
    'm_min_to_mm_s',
    'mm_s_to_m_min'
]
