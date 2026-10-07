// Spike S: wl-xcon's exact drawer (wl_xcon/exact.py) for one Gabor seen by each eye
// through the stereoscope, plus two flat light-sensor patches. One invocation per panel
// pixel; the output is CIE Y in cd/m², row-major, top row first.

struct Params {
    // Per eye: the item's direction c and its own rightward and upward axes ex, ey
    // (viewport.center, viewport.local_true_angle), computed on the host in f64.
    c_left: vec4<f32>, ex_left: vec4<f32>, ey_left: vec4<f32>,
    c_right: vec4<f32>, ex_right: vec4<f32>, ey_right: vec4<f32>,
    panel_w: u32, panel_h: u32, vp_w: u32, vp_h: u32,
    pitch_x: f32, pitch_y: f32, distance: f32, ahead_x: f32,
    ahead_y: f32, background: f32, opacity: f32, radius: f32,
    sigma: f32, sf: f32, phase: f32, michelson: f32,  // phase in radians
    cos_o: f32, sin_o: f32, patch_px: u32, patch_y: f32,
}

var<immediate> p: Params;
@group(0) @binding(0) var<storage, read_write> out: array<f32>;

const N: i32 = 4;       // exact.SUPERSAMPLE
const M: i32 = 6;       // N + 2: the pixel's samples and one ring of neighbors
const PI: f32 = 3.14159265358979;

struct Local { u: f32, w: f32, d: f32 }

// A sample's local coordinates (u, w) in degrees about the item, turned by −orientation,
// and its signed distance to the circle. (sx, sy) indexes the eye's sample grid.
fn local(sx: i32, sy: i32, c: vec3<f32>, ex: vec3<f32>, ey: vec3<f32>) -> Local {
    let x_cm = ((f32(sx) + 0.5) / f32(N) - f32(p.vp_w) / 2.0) * p.pitch_x - p.ahead_x;
    let y_cm = (f32(p.vp_h) / 2.0 - (f32(sy) + 0.5) / f32(N)) * p.pitch_y - p.ahead_y;
    let v = normalize(vec3(x_cm, y_cm, p.distance));
    // Azimuthal-equidistant about c: the angle from c, split along ex and ey. t = v − (v·c)c
    // lies in the ex–ey plane, so t·ex = v·ex and |t| = hypot(v·ex, v·ey).
    let a = dot(v, ex);
    let b = dot(v, ey);
    let tn = sqrt(a * a + b * b);
    let s = select(0.0, degrees(atan2(tn, dot(v, c))) / tn, tn > 0.0);
    let u = s * a * p.cos_o + s * b * p.sin_o;
    let w = -s * a * p.sin_o + s * b * p.cos_o;
    return Local(u, w, sqrt(u * u + w * w) - p.radius);
}

// exact._slope: the larger of the forward and backward differences; at the sample
// grid's edge, the one that exists.
fn slope(before: f32, here: f32, after: f32, has_before: bool, has_after: bool) -> f32 {
    let back = select(0.0, abs(here - before), has_before);
    let ahead = select(0.0, abs(after - here), has_after);
    return max(back, ahead);
}

@compute @workgroup_size(8, 8)
fn main(@builtin(global_invocation_id) id: vec3<u32>) {
    if (id.x >= p.panel_w || id.y >= p.panel_h) { return; }
    let index = id.y * p.panel_w + id.x;
    // The light-sensor patches: flat squares at both bottom corners, over everything.
    if (id.y >= p.panel_h - p.patch_px && (id.x < p.patch_px || id.x >= p.panel_w - p.patch_px)) {
        out[index] = p.patch_y;
        return;
    }
    let right = id.x >= p.vp_w;  // the right eye sees the panel's right half
    let c = select(p.c_left, p.c_right, right).xyz;
    let ex = select(p.ex_left, p.ex_right, right).xyz;
    let ey = select(p.ey_left, p.ey_right, right).xyz;
    let col = i32(id.x % p.vp_w);
    let row = i32(id.y);

    var u: array<f32, 36>;  // M × M
    var w: array<f32, 36>;
    var d: array<f32, 36>;
    for (var j = 0; j < M; j++) {
        for (var i = 0; i < M; i++) {
            let l = local(col * N + i - 1, row * N + j - 1, c, ex, ey);
            u[j * M + i] = l.u;
            w[j * M + i] = l.w;
            d[j * M + i] = l.d;
        }
    }

    let last_x = i32(p.vp_w) * N - 1;
    let last_y = i32(p.vp_h) * N - 1;
    var sum = 0.0;
    for (var j = 1; j <= N; j++) {
        for (var i = 1; i <= N; i++) {
            let k = j * M + i;
            let sx = col * N + i - 1;
            let sy = row * N + j - 1;
            // exact.coverage: the sample's share inside, clip(0.5 − d / |∇d|, 0, 1).
            let gx = slope(d[k - 1], d[k], d[k + 1], sx > 0, sx < last_x);
            let gy = slope(d[k - M], d[k], d[k + M], sy > 0, sy < last_y);
            let g = sqrt(gx * gx + gy * gy);
            var cover = select(0.0, 1.0, d[k] <= 0.0);
            if (g > 0.0) { cover = clamp(0.5 - d[k] / g, 0.0, 1.0); }
            let a = cover * p.opacity;
            // The Gaussian edge applies to contrast; the grating covers, about what is below.
            let envelope = exp(-(u[k] * u[k] + w[k] * w[k]) / (2.0 * p.sigma * p.sigma));
            let below = p.background;
            let light = below * (1.0 + p.michelson * sin(2.0 * PI * p.sf * w[k] + p.phase) * envelope);
            sum += below + a * (light - below);
        }
    }
    out[index] = sum / f32(N * N);
}
