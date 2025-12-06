"""
Motion Planner Module - Realistic cutting time estimation.

Based on lookahead algorithm with trapezoidal velocity profile,
similar to GRBL/Klipper CNC controllers.

Key concepts:
- v_max: maximum cutting speed (from material/thickness tables)
- a_max: maximum acceleration (machine profile)
- square_corner_velocity: speed limit at 90-degree corners
- forward-backward pass: velocity planning respecting acc/dec limits
- trapezoidal profile: acc -> cruise -> dec for each segment
"""

import math
from typing import List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class MotionSegment:
    """Single motion segment (line or arc approximation)."""
    length_mm: float
    start_angle_deg: Optional[float] = None  # Direction at start
    end_angle_deg: Optional[float] = None    # Direction at end
    is_rapid: bool = False                   # Rapid move (laser OFF)
    contour_id: int = 0                      # Contour ID (each closed shape is a contour)


@dataclass
class MachineProfile:
    """Machine dynamics parameters."""
    max_accel_mm_s2: float = 2000.0          # Max acceleration [mm/s^2]
    max_rapid_mm_s: float = 500.0            # Max rapid speed [mm/s]
    square_corner_velocity_mm_s: float = 50.0  # Speed limit at 90-deg corner
    junction_deviation_mm: float = 0.05       # Alternative corner model
    use_junction_deviation: bool = False      # Use junction deviation model


def corner_speed_limit(angle_deg: float, v_corner_90: float, v_max: float) -> float:
    """
    Calculate speed limit at a corner based on corner angle.

    Args:
        angle_deg: Angle between incoming and outgoing vectors (0=reversal, 180=straight)
        v_corner_90: Speed limit at 90-degree corner [mm/s]
        v_max: Maximum cutting speed [mm/s]

    Returns:
        Speed limit at this corner [mm/s]
    """
    a = max(0.0, min(180.0, angle_deg))

    # Straight through - no limit
    if a >= 179.0:
        return v_max

    # Scale based on angle: 90deg => 1.0, 180deg => 2.0
    # Sharper angles (<90deg) get lower limits
    scale = 1.0 + (a - 90.0) / 90.0

    return min(v_max, v_corner_90 * max(0.2, scale))


def junction_deviation_speed(angle_deg: float, deviation_mm: float,
                              a_max: float, v_max: float) -> float:
    """
    Alternative corner model using junction deviation.
    Used by Marlin/Klipper for smoother motion.

    Args:
        angle_deg: Corner angle (0=reversal, 180=straight)
        deviation_mm: Maximum allowed deviation from path
        a_max: Maximum acceleration
        v_max: Maximum speed

    Returns:
        Speed limit at this junction [mm/s]
    """
    if angle_deg >= 179.0:
        return v_max

    # Convert to radians and calculate half-angle
    theta = math.radians(180.0 - angle_deg)
    half_theta = theta / 2.0

    if half_theta < 0.001:  # Nearly straight
        return v_max

    # Junction speed formula from Klipper
    sin_half = math.sin(half_theta)
    cos_half = math.cos(half_theta)

    if sin_half < 0.001:
        return v_max

    R = deviation_mm * sin_half / (1.0 - cos_half)
    v_junction = math.sqrt(a_max * R)

    return min(v_max, v_junction)


def calculate_junction_angles(segments: List[MotionSegment]) -> List[float]:
    """
    Calculate angles at junctions between segments.

    Returns:
        List of angles at junctions (length = len(segments) + 1)
        First and last are 0 (start/stop)
    """
    n = len(segments)
    angles = [0.0] * (n + 1)  # 0 at start (from stop), 0 at end (to stop)

    for i in range(1, n):
        prev_seg = segments[i - 1]
        curr_seg = segments[i]

        if prev_seg.end_angle_deg is not None and curr_seg.start_angle_deg is not None:
            # Calculate angle between vectors
            diff = abs(curr_seg.start_angle_deg - prev_seg.end_angle_deg)
            if diff > 180.0:
                diff = 360.0 - diff
            angles[i] = 180.0 - diff
        else:
            # Unknown - assume 90 degrees (conservative)
            angles[i] = 90.0

    return angles


def plan_speeds(lengths: List[float], v_junction: List[float],
                v_max: float, a_max: float) -> List[float]:
    """
    Forward-backward pass to plan velocities respecting acc/dec limits.

    This is the core lookahead algorithm used in CNC controllers.

    Args:
        lengths: Segment lengths [mm], n segments
        v_junction: Speed limits at junctions [mm/s], n+1 values
        v_max: Maximum cutting speed [mm/s]
        a_max: Maximum acceleration [mm/s^2]

    Returns:
        Planned velocities at junctions [mm/s], n+1 values
    """
    n = len(lengths)
    if n == 0:
        return [0.0]

    V = [0.0] * (n + 1)
    V[0] = 0.0  # Start from stop

    # Forward pass: respect acceleration from previous junction
    for k in range(1, n):
        # Maximum speed reachable from previous junction
        v_reach = math.sqrt(V[k-1]**2 + 2 * a_max * lengths[k-1])
        V[k] = min(v_reach, v_junction[k], v_max)

    V[n] = 0.0  # End at stop

    # Backward pass: respect deceleration to next junction
    for k in reversed(range(0, n)):
        # Maximum speed allowing deceleration to next junction
        v_reach = math.sqrt(V[k+1]**2 + 2 * a_max * lengths[k])
        V[k] = min(V[k], v_reach)

    return V


def segment_time_trapezoid(length: float, v_start: float, v_end: float,
                           v_max: float, a_max: float) -> float:
    """
    Calculate time for a single segment using trapezoidal profile.

    Profile: acceleration -> cruise (if reached v_max) -> deceleration

    Args:
        length: Segment length [mm]
        v_start: Entry velocity [mm/s]
        v_end: Exit velocity [mm/s]
        v_max: Maximum velocity [mm/s]
        a_max: Maximum acceleration [mm/s^2]

    Returns:
        Time to traverse segment [s]
    """
    if length <= 0:
        return 0.0

    if a_max <= 0:
        # No acceleration - constant speed
        return length / max(1e-9, v_max)

    # Calculate peak velocity (triangular or trapezoidal)
    v_peak_sq = a_max * length + 0.5 * (v_start**2 + v_end**2)
    v_peak = min(v_max, math.sqrt(max(0.0, v_peak_sq)))

    # Acceleration phase
    t1 = max(0.0, (v_peak - v_start) / a_max)
    s1 = max(0.0, (v_peak**2 - v_start**2) / (2 * a_max))

    # Deceleration phase
    t3 = max(0.0, (v_peak - v_end) / a_max)
    s3 = max(0.0, (v_peak**2 - v_end**2) / (2 * a_max))

    # Cruise phase (remaining distance at v_peak)
    s2 = max(0.0, length - s1 - s3)
    t2 = s2 / max(1e-9, v_peak)

    return t1 + t2 + t3


def effective_vmax(v_max: float, short_segment_ratio: float, k: float = 0.7) -> float:
    """
    Reduce effective max speed based on proportion of short segments.

    Parts with many small features (holes, intricate patterns) will have
    lower effective speed because machine can't accelerate to full speed.

    Args:
        v_max: Nominal max cutting speed [mm/s]
        short_segment_ratio: Ratio of short segments (0-1)
        k: Penalty factor (0.7 = 70% penalty at ratio=1)

    Returns:
        Effective max speed [mm/s]
    """
    # Minimum 30% of v_max even with all short segments
    return max(0.3 * v_max, v_max * (1.0 - k * short_segment_ratio))


def estimate_motion_time(segments: List[MotionSegment],
                         machine: MachineProfile,
                         v_max_cutting: float) -> Tuple[float, float]:
    """
    Estimate total motion time for a toolpath.

    Args:
        segments: List of motion segments
        machine: Machine profile with dynamics parameters
        v_max_cutting: Maximum cutting speed for this material [mm/s]

    Returns:
        Tuple of (cutting_time_s, rapid_time_s)
    """
    if not segments:
        return 0.0, 0.0

    # Separate cutting and rapid moves
    cutting_segments = [s for s in segments if not s.is_rapid]
    rapid_segments = [s for s in segments if s.is_rapid]

    cutting_time = _estimate_segment_group_time(
        cutting_segments, machine, v_max_cutting
    )

    rapid_time = _estimate_segment_group_time(
        rapid_segments, machine, machine.max_rapid_mm_s
    )

    return cutting_time, rapid_time


def _estimate_segment_group_time(segments: List[MotionSegment],
                                  machine: MachineProfile,
                                  v_max: float) -> float:
    """Estimate time for a group of segments."""
    if not segments:
        return 0.0

    # Group segments by contour_id - each contour requires separate start/stop
    contours = {}
    for seg in segments:
        cid = seg.contour_id
        if cid not in contours:
            contours[cid] = []
        contours[cid].append(seg)

    total_time = 0.0

    # Process each contour separately (each starts and ends at V=0)
    for contour_id, contour_segments in contours.items():
        contour_time = _estimate_single_contour_time(
            contour_segments, machine, v_max
        )
        total_time += contour_time

    return total_time


def _estimate_single_contour_time(segments: List[MotionSegment],
                                   machine: MachineProfile,
                                   v_max: float) -> float:
    """
    Estimate time for a single contour (closed shape).

    Each contour starts from V=0 (after pierce) and ends at V=0.
    This is critical for accurate time estimation on parts with many holes.
    """
    if not segments:
        return 0.0

    lengths = [s.length_mm for s in segments]
    angles = calculate_junction_angles(segments)

    # Calculate junction speed limits
    v_junction = []
    for angle in angles:
        if machine.use_junction_deviation:
            v = junction_deviation_speed(
                angle, machine.junction_deviation_mm,
                machine.max_accel_mm_s2, v_max
            )
        else:
            v = corner_speed_limit(
                angle, machine.square_corner_velocity_mm_s, v_max
            )
        v_junction.append(v)

    # IMPORTANT: First and last junction MUST be 0 (start/stop for each contour)
    v_junction[0] = 0.0
    v_junction[-1] = 0.0

    # Plan speeds with lookahead
    planned_v = plan_speeds(lengths, v_junction, v_max, machine.max_accel_mm_s2)

    # Calculate time for each segment
    contour_time = 0.0
    for i, length in enumerate(lengths):
        t = segment_time_trapezoid(
            length, planned_v[i], planned_v[i+1],
            v_max, machine.max_accel_mm_s2
        )
        contour_time += t

    return contour_time


def estimate_simple_time(cut_length_mm: float, pierce_count: int,
                         short_segment_ratio: float,
                         v_max_m_min: float, a_max_mm_s2: float,
                         v_corner_90_mm_s: float,
                         pierce_time_s: float) -> float:
    """
    Simplified time estimation without full toolpath data.

    Uses heuristics based on:
    - Total cutting length
    - Number of pierces (contour starts)
    - Short segment ratio (complexity indicator)

    Args:
        cut_length_mm: Total cutting length [mm]
        pierce_count: Number of pierces/contours
        short_segment_ratio: Ratio of short segments (0-1)
        v_max_m_min: Max cutting speed [m/min]
        a_max_mm_s2: Max acceleration [mm/s^2]
        v_corner_90_mm_s: Corner speed at 90 deg [mm/s]
        pierce_time_s: Time per pierce [s]

    Returns:
        Estimated cutting time [s]
    """
    # Convert v_max to mm/s
    v_max_mm_s = v_max_m_min * 1000.0 / 60.0

    # Reduce effective speed based on complexity
    v_eff = effective_vmax(v_max_mm_s, short_segment_ratio)

    # Estimate average speed accounting for acc/dec
    # Heuristic: assume average segment is 20mm, corners every ~50mm
    avg_segment_mm = 20.0
    corners_per_mm = 1.0 / 50.0

    # Time for straight motion at effective speed
    straight_time = cut_length_mm / v_eff

    # Add overhead for acceleration phases
    # Each contour start needs acceleration from zero
    accel_overhead_per_pierce = v_eff / a_max_mm_s2  # Time to reach v_eff

    # Corner slowdowns
    num_corners = cut_length_mm * corners_per_mm
    corner_speed_reduction = (v_eff - v_corner_90_mm_s) / v_eff
    corner_time_overhead = num_corners * (avg_segment_mm / v_eff) * corner_speed_reduction * 0.5

    motion_time = straight_time + pierce_count * accel_overhead_per_pierce + corner_time_overhead

    # Pierce time
    total_pierce_time = pierce_count * pierce_time_s

    return motion_time + total_pierce_time


# Unit conversion helpers
def m_min_to_mm_s(v_m_min: float) -> float:
    """Convert m/min to mm/s."""
    return v_m_min * 1000.0 / 60.0


def mm_s_to_m_min(v_mm_s: float) -> float:
    """Convert mm/s to m/min."""
    return v_mm_s * 60.0 / 1000.0
