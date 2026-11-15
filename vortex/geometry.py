"""Rotation helpers.

Conventions used everywhere in Vortex:
- Quaternions are Hamilton, stored as (w, x, y, z), unit norm.
- A pose quaternion q_wb rotates vectors from the body frame into the world frame: v_w = R(q_wb) v_b.
- Angular velocity from a gyroscope is expressed in the body frame.
"""

from __future__ import annotations

import numpy as np


def quat_normalize(q: np.ndarray) -> np.ndarray:
    q = np.asarray(q, dtype=float)
    n = np.linalg.norm(q, axis=-1, keepdims=True)
    return q / n


def quat_multiply(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Hamilton product a * b for (..., 4) arrays in (w, x, y, z) order."""
    aw, ax, ay, az = np.moveaxis(np.asarray(a, dtype=float), -1, 0)
    bw, bx, by, bz = np.moveaxis(np.asarray(b, dtype=float), -1, 0)
    return np.stack(
        [
            aw * bw - ax * bx - ay * by - az * bz,
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
        ],
        axis=-1,
    )


def quat_conjugate(q: np.ndarray) -> np.ndarray:
    q = np.asarray(q, dtype=float)
    return q * np.array([1.0, -1.0, -1.0, -1.0])


def quat_from_rotvec(rv: np.ndarray) -> np.ndarray:
    """Exponential map: rotation vector (axis * angle, radians) to quaternion."""
    rv = np.asarray(rv, dtype=float)
    angle = np.linalg.norm(rv, axis=-1, keepdims=True)
    half = 0.5 * angle
    # sin(half)/angle, with the small-angle limit 0.5 - angle^2/48.
    small = angle < 1e-8
    safe = np.where(small, 1.0, angle)
    k = np.where(small, 0.5 - angle**2 / 48.0, np.sin(half) / safe)
    return np.concatenate([np.cos(half), rv * k], axis=-1)


def quat_to_rotvec(q: np.ndarray) -> np.ndarray:
    """Logarithm map: quaternion to rotation vector (shortest rotation)."""
    q = quat_normalize(q)
    q = np.where(q[..., :1] < 0, -q, q)
    w = np.clip(q[..., :1], -1.0, 1.0)
    v = q[..., 1:]
    s = np.linalg.norm(v, axis=-1, keepdims=True)
    angle = 2.0 * np.arctan2(s, w)
    small = s < 1e-8
    k = np.where(small, 2.0, angle / np.where(small, 1.0, s))
    return v * k


def quat_to_matrix(q: np.ndarray) -> np.ndarray:
    """(..., 4) quaternions to (..., 3, 3) rotation matrices."""
    w, x, y, z = np.moveaxis(quat_normalize(q), -1, 0)
    return np.stack(
        [
            np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)], axis=-1),
            np.stack([2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)], axis=-1),
            np.stack([2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)], axis=-1),
        ],
        axis=-2,
    )


def matrix_to_quat(m: np.ndarray) -> np.ndarray:
    """Single 3x3 rotation matrix to a (w, x, y, z) quaternion with w >= 0."""
    m = np.asarray(m, dtype=float)
    tr = np.trace(m)
    if tr > 0:
        s = 2.0 * np.sqrt(tr + 1.0)
        q = [0.25 * s, (m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s]
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = 2.0 * np.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2])
        q = [(m[2, 1] - m[1, 2]) / s, 0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s]
    elif m[1, 1] > m[2, 2]:
        s = 2.0 * np.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2])
        q = [(m[0, 2] - m[2, 0]) / s, (m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s]
    else:
        s = 2.0 * np.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1])
        q = [(m[1, 0] - m[0, 1]) / s, (m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s]
    q = quat_normalize(np.array(q))
    return -q if q[0] < 0 else q


def quat_slerp_series(t_src: np.ndarray, q_src: np.ndarray, t_dst: np.ndarray) -> np.ndarray:
    """Interpolate a quaternion series to new timestamps (clamped at the ends)."""
    t_src = np.asarray(t_src, dtype=float)
    q_src = quat_normalize(q_src)
    t_dst = np.clip(np.asarray(t_dst, dtype=float), t_src[0], t_src[-1])
    idx = np.clip(np.searchsorted(t_src, t_dst, side="right") - 1, 0, len(t_src) - 2)
    t0, t1 = t_src[idx], t_src[idx + 1]
    span = np.where(t1 > t0, t1 - t0, 1.0)
    u = ((t_dst - t0) / span)[:, None]
    q0, q1 = q_src[idx], q_src[idx + 1]
    # Take the short way round.
    q1 = np.where(np.sum(q0 * q1, axis=-1, keepdims=True) < 0, -q1, q1)
    delta = quat_to_rotvec(quat_multiply(quat_conjugate(q0), q1))
    return quat_normalize(quat_multiply(q0, quat_from_rotvec(delta * u)))
