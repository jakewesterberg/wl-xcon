"""Spike S: compare the GPU's panel (gpu-out/panel_y.f32) with wl-xcon's exact drawer,
region by region, and check the patches and the background directly.

usage: compare.py <panel_y.f32> <out-dir>"""
import json, math, sys, time
from pathlib import Path

import numpy as np

from resolve_scene import scene
from wl_xcon import exact

STEP = 100.0 / 1023.0  # STAND-IN: one 10-bit step of a linear 0-100 cd/m² scale
PATCH, PATCH_Y = 200, 100.0

s, vps = scene()
(item,) = s.items
W, H = vps[0].width_px * 2, vps[0].height_px
bg = s.background_left[1]
gpu = np.fromfile(sys.argv[1], dtype="<f4").reshape(H, W).astype(np.float64)
out = Path(sys.argv[2]); out.mkdir(exist_ok=True)


def center_px(vp, x_deg, y_deg):
    col = vp.width_px / 2 + (vp.distance_cm * math.tan(math.radians(x_deg)) + vp.ahead_cm[0]) / vp.pitch_cm[0]
    row = vp.height_px / 2 - (vp.distance_cm * math.tan(math.radians(y_deg)) + vp.ahead_cm[1]) / vp.pitch_cm[1]
    return col, row


regions = []  # (label, eye index, (x0, y0, x1, y1) in that eye's pixels)
for e, vp in enumerate(vps):
    col, row = center_px(vp, *(item.at_left if vp.eye == "left" else item.at_right))
    c, r = int(round(col)), int(round(row))
    regions.append((f"gabor-{vp.eye}", e, (c - 200, r - 200, c + 200, r + 200)))
regions += [
    ("bg-left-top-left-corner", 0, (0, 0, 64, 64)),
    ("bg-left-center", 0, (928, 1048, 992, 1112)),
    ("bg-left-at-seam", 0, (1856, 1048, 1920, 1112)),
    ("bg-right-at-seam", 1, (0, 1048, 64, 1112)),
    ("bg-right-upper-right", 1, (1500, 300, 1564, 364)),
    ("bg-right-above-patch", 1, (1720, 1896, 1784, 1960)),
]

report = {"step_cd_m2_STAND_IN": STEP, "background": bg, "regions": []}
covered = np.zeros((H, W), bool)
for label, e, (x0, y0, x1, y1) in regions:
    vp = vps[e]
    t0 = time.time()
    ref = exact.draw(s, vp, region=(x0, y0, x1, y1))[..., 1]
    secs = time.time() - t0
    np.save(out / f"exact_{label}.npy", ref)
    off = e * vp.width_px
    g = gpu[y0:y1, off + x0: off + x1]
    covered[y0:y1, off + x0: off + x1] = True
    dy = g - ref
    a = np.abs(dy)
    i = np.unravel_index(np.argmax(a), a.shape)
    lit = ref != bg
    border = np.concatenate([ref[0], ref[-1], ref[:, 0], ref[:, -1]])
    row = {
        "region": label, "eye": vp.eye, "eye_px": [x0, y0, x1, y1],
        "panel_cols": [off + x0, off + x1 - 1], "panel_rows": [y0, y1 - 1],
        "max_abs_dY": float(a.max()), "max_at_panel_row_col": [int(y0 + i[0]), int(off + x0 + i[1])],
        "exact_there": float(ref[i]), "gpu_there": float(g[i]),
        "max_in_steps": float(a.max() / STEP), "mean_abs_dY": float(a.mean()),
        "mean_abs_dY_where_exact_is_not_background": float(a[lit].mean()) if lit.any() else None,
        "mean_signed_dY": float(dy.mean()), "pixels": int(a.size), "pixels_not_background": int(lit.sum()),
        "pixels_exactly_equal": int((dy == 0).sum()),
        "exact_border_all_background": bool((border == bg).all()),
        "exact_min_max": [float(ref.min()), float(ref.max())],
        "exact_draw_seconds": round(secs, 1),
    }
    report["regions"].append(row)
    print(json.dumps(row))

# The patches, directly: every patch pixel is 100, and the ring just outside them is not.
p_left = gpu[H - PATCH:, :PATCH]
p_right = gpu[H - PATCH:, W - PATCH:]
ring = np.concatenate([gpu[H - PATCH - 1, :PATCH + 1], gpu[H - PATCH:, PATCH],
                       gpu[H - PATCH - 1, W - PATCH - 1:], gpu[H - PATCH:, W - PATCH - 1]])
report["patches"] = {
    "left_all_100": bool((p_left == PATCH_Y).all()), "right_all_100": bool((p_right == PATCH_Y).all()),
    "ring_just_outside_all_background": bool((ring == bg).all()),
    "pixels_equal_100_anywhere": int((gpu == PATCH_Y).sum()), "expected": 2 * PATCH * PATCH,
}
covered[H - PATCH:, :PATCH] = covered[H - PATCH:, W - PATCH:] = True
# Everything else on the GPU's panel: the exact drawer is the background there, since
# every pixel is more than 50 px (0.7 degrees) outside the Gabor's cut-off circle.
rest = gpu[~covered]
report["rest_of_panel"] = {
    "pixels": int(rest.size), "all_exactly_background": bool((rest == bg).all()),
    "max_abs_dY": float(np.abs(rest - bg).max()),
}
report["gpu_panel"] = {"finite": bool(np.isfinite(gpu).all()), "min": float(gpu.min()), "max": float(gpu.max())}
print(json.dumps({k: report[k] for k in ("patches", "rest_of_panel", "gpu_panel")}))
(out / "compare.json").write_text(json.dumps(report, indent=1))
