"""Spike S: resolve the scene on the Mac with wl-xcon's own `screen.resolve`, and write
the resolved numbers the GPU program reads (scene.txt). The GPU never re-implements
resolve."""
import json, sys
from _rig import RIG, STEREOSCOPE
from wl_xcon import screen, viewport, look
from wl_xcon.photometry import Gray, Michelson, to_xyz
from wl_xcon.task import Gabor, Stimulus, Trial

TRIAL = Trial(start="s", states=[], background=Gray(20.0))
STIM = Stimulus("g", at=(2.0, 1.0), disparity=-0.2,
                looks=Gabor(sf=2.0, sigma=0.5, phase=30.0, orientation=30.0, contrast=Michelson(0.5)))


def scene():
    s = screen.resolve({STIM.name: STIM}, {}, TRIAL, STEREOSCOPE, frame_period=1 / 240, frame=0)
    vps = viewport.viewports(RIG, STEREOSCOPE)
    return s, vps


if __name__ == "__main__":
    s, vps = scene()
    (item,) = s.items
    assert isinstance(item.shape, look.Circle) and isinstance(item.edge, look.GaussianEdge)
    assert item.edge.applies == "contrast" and item.combine == "cover" and item.fill.mean_xyz is None
    assert s.periphery == "true_angle", s.periphery
    print("item:", item, file=sys.stderr)
    print("background_left/right:", s.background_left, s.background_right, file=sys.stderr)
    print("viewports:", vps, file=sys.stderr)
    vl, vr = vps
    out = dict(
        panel_w=RIG.pixels[0], panel_h=RIG.pixels[1],
        vp_w=vl.width_px, vp_h=vl.height_px, pitch_x=vl.pitch_cm[0], pitch_y=vl.pitch_cm[1],
        distance=vl.distance_cm, ahead_x=vl.ahead_cm[0], ahead_y=vl.ahead_cm[1],
        bg_y=s.background_left[1],
        left_x=item.at_left[0], left_y=item.at_left[1],
        right_x=item.at_right[0], right_y=item.at_right[1],
        orientation=item.orientation, radius=item.shape.size / 2, sigma=item.edge.sigma,
        sf=item.fill.sf, phase=item.fill.phase, michelson=item.fill.michelson,
        tf=item.fill.tf, opacity=item.opacity, patch_y=100.0,
    )
    assert vl.ahead_cm == vr.ahead_cm and s.background_left == s.background_right
    assert out["tf"] == 0.0
    for k, v in out.items():
        print(f"{k} {v!r}")
