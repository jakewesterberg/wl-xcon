//! Spike S part 2: when does each frame reach the display? Drives the monitor directly
//! (VK_KHR_display display-plane surface, no compositor), presents a fixed number of frames on a
//! FIFO swapchain - a steady gray field with one 100 px square in the bottom-left corner that
//! alternates black/white each frame - and records per frame the CPU time of the present call
//! (CLOCK_MONOTONIC), the driver's present-stage times (VK_EXT_present_timing, calibrated to
//! CLOCK_MONOTONIC), and the vblank counter (VK_EXT_display_control).
//!
//! If the display cannot be taken (another program holds it), it exits at once with code 2,
//! having changed nothing. Ctrl+C stops it and still releases the display; a watchdog ends it 60 s
//! after start whatever happens. Nothing is printed while it holds the display.

#![allow(unsafe_op_in_unsafe_fn)] // the Vulkan calls are unsafe throughout

mod ffi;
mod layout_check;

use ash::{ext, khr, vk};
use ffi::*;
use std::ffi::{CStr, c_void};
use std::fmt::Write as _;
use std::sync::atomic::{AtomicI32, Ordering::SeqCst};
use std::time::Duration;

const USAGE: &str = "usage: timing [--list] [--frames N] [--mode WxH@HZ] [--display NAME] [--out DIR] [--hold-ms MS] [--headless]";
const GRAY: f32 = 64.0 / 255.0; // the field, as an 8-bit code value
const SQUARE: u32 = 100; // the photodiode square, px
const MAX_RUN_S: f64 = 50.0; // the longest run accepted, at the chosen mode's nominal rate
const WATCHDOG_S: u64 = 60; // hard limit; a stop is requested 5 s before it
const IN_FLIGHT: usize = 2;
const TIMING_QUEUE: u32 = 256;
const BATCH: usize = 64;

/// What asked the program to stop: a signal number, or -1 for the watchdog.
static STOP: AtomicI32 = AtomicI32::new(0);

unsafe extern "C" {
    fn signal(sig: i32, handler: extern "C" fn(i32)) -> usize;
    fn _exit(code: i32) -> !;
    fn clock_gettime(clock: i32, ts: *mut [i64; 2]) -> i32;
}

/// First signal: stop at the next check and release the display. Second: leave at once
/// (the kernel releases the display when the process ends).
extern "C" fn on_signal(sig: i32) {
    if STOP.swap(sig, SeqCst) != 0 {
        unsafe { _exit(128 + sig) }
    }
}

/// CLOCK_MONOTONIC in ns (the clock VK_TIME_DOMAIN_CLOCK_MONOTONIC_KHR names).
fn now() -> u64 {
    let mut ts = [0i64; 2];
    unsafe { clock_gettime(1, &mut ts) };
    (ts[0] * 1_000_000_000 + ts[1]) as u64
}

struct Opts { list: bool, frames: usize, mode: Option<(u32, u32, f64)>, display: String, out: String, hold_ms: u64, headless: bool }

fn parse() -> Result<Opts, String> {
    let home = std::env::var("HOME").unwrap_or_default();
    let mut o = Opts { list: false, frames: 1200, mode: None, display: "DP-0".into(), out: format!("{home}/wl-spike-s/timing/out"), hold_ms: 0, headless: false };
    let mut args = std::env::args().skip(1);
    while let Some(a) = args.next() {
        let mut val = || args.next().ok_or(format!("{a} needs a value"));
        match a.as_str() {
            "--list" => o.list = true,
            "--headless" => o.headless = true, // test: an off-screen surface, nothing on the display
            "--frames" => o.frames = val()?.parse().map_err(|_| "--frames: a whole number")?,
            "--display" => o.display = val()?,
            "--out" => o.out = val()?,
            "--hold-ms" => o.hold_ms = val()?.parse().map_err(|_| "--hold-ms: a whole number")?,
            "--mode" => {
                let v = val()?;
                let (wh, hz) = v.split_once('@').ok_or("--mode: WxH@HZ, e.g. 3840x2160@119.88")?;
                let (w, h) = wh.split_once('x').ok_or("--mode: WxH@HZ")?;
                let num = |s: &str| s.parse::<f64>().map_err(|_| format!("--mode: bad number {s}"));
                o.mode = Some((num(w)? as u32, num(h)? as u32, num(hz)?));
            }
            "-h" | "--help" => return Err(String::new()),
            _ => return Err(format!("unknown option {a}")),
        }
    }
    if o.frames < 2 { return Err("--frames: at least 2".into()); }
    Ok(o)
}

enum Fail { Refused(String), Stopped, Error(String) }
type R<T> = Result<T, Fail>;
fn error(what: &'static str) -> impl Fn(vk::Result) -> Fail { move |r| Fail::Error(format!("{what}: {r:?}")) }
fn stop_requested() -> R<()> { if STOP.load(SeqCst) != 0 { Err(Fail::Stopped) } else { Ok(()) } }

fn main() {
    let o = match parse() {
        Ok(o) => o,
        Err(e) => { eprintln!("{}{USAGE}", if e.is_empty() { String::new() } else { format!("timing: {e}\n") }); std::process::exit(e.is_empty() as i32 ^ 1) }
    };
    for sig in [1, 2, 15] { unsafe { signal(sig, on_signal) }; } // SIGHUP, SIGINT, SIGTERM
    std::thread::spawn(|| {
        std::thread::sleep(Duration::from_secs(WATCHDOG_S - 5));
        let _ = STOP.compare_exchange(0, -1, SeqCst, SeqCst);
        std::thread::sleep(Duration::from_secs(5));
        eprintln!("timing: watchdog: still running {WATCHDOG_S} s after start; forcing exit");
        unsafe { _exit(124) }
    });
    let code = match unsafe { measure(&o) } {
        Ok(None) => 0,
        Ok(Some(rep)) => report(&o, &rep),
        Err(Fail::Refused(m)) => { eprintln!("timing: cannot take the display ({m}); another program, such as the desktop or the login screen, probably holds it. Nothing was changed."); 2 }
        Err(Fail::Stopped) => { eprintln!("timing: stopped before taking the display; nothing was changed."); stop_code() }
        Err(Fail::Error(m)) => { eprintln!("timing: error: {m}"); 1 }
    };
    std::process::exit(code)
}

fn stop_code() -> i32 { match STOP.load(SeqCst) { -1 => 124, 0 => 0, s => 128 + s } }

/// Everything the program creates, destroyed in reverse order when dropped - on success, on
/// refusal, on Ctrl+C, and on panic.
struct Session {
    _entry: ash::Entry,
    instance: ash::Instance,
    gpu: vk::PhysicalDevice,
    surface_i: khr::surface::Instance,
    release_i: Option<ext::direct_mode_display::Instance>,
    device: Option<ash::Device>,
    swapchain_d: Option<khr::swapchain::Device>,
    surface: vk::SurfaceKHR,
    swapchain: vk::SwapchainKHR,
    display: vk::DisplayKHR,
    acquired: bool,
    drm: Option<std::fs::File>,
    pool: vk::CommandPool,
    buffers: Vec<(vk::Buffer, vk::DeviceMemory)>,
    semaphores: Vec<vk::Semaphore>,
    fences: Vec<vk::Fence>,
}

impl Drop for Session {
    fn drop(&mut self) {
        unsafe {
            if let Some(d) = &self.device {
                let _ = d.device_wait_idle();
                self.fences.iter().for_each(|&f| d.destroy_fence(f, None));
                self.semaphores.iter().for_each(|&s| d.destroy_semaphore(s, None));
                d.destroy_command_pool(self.pool, None);
                for &(b, m) in &self.buffers { d.destroy_buffer(b, None); d.free_memory(m, None); }
                if let Some(sd) = &self.swapchain_d { sd.destroy_swapchain(self.swapchain, None); }
            }
            self.surface_i.destroy_surface(self.surface, None);
            if self.acquired {
                if let Some(r) = &self.release_i { let _ = (r.fp().release_display_ext)(self.gpu, self.display); }
            }
            if let Some(d) = self.device.take() { d.destroy_device(None); }
            self.drm.take(); // closes the DRM node, after the release
            self.instance.destroy_instance(None);
        }
    }
}

#[derive(Clone, Copy, Default)]
struct Frame { image: u32, t_call: u64, t_return: u64, result: i32, vblank: Option<u64>, got: bool, complete: bool, domain: i32, domain_id: u64, stage: [u64; 4] }

/// Calibrated pair: CLOCK_MONOTONIC and the present-timing domain, per stage (ns), with the
/// driver's maximum deviation.
#[derive(Clone, Copy, Default)]
struct Calib { ok: bool, mono: u64, dom: [u64; 4], dev: u64 }
impl Calib { fn offset(&self, k: usize) -> i64 { self.mono as i64 - self.dom[k] as i64 } }

struct Report {
    header: Vec<String>,
    notes: Vec<String>,
    frames: Vec<Frame>,
    requested: usize,
    nominal_ns: f64,
    refresh: Option<(u64, u64)>,
    domain: Option<(i32, u64)>,
    queries: u32,
    calib: [Calib; 2],
    stopped: i32,
}

fn domain_name(d: i32) -> String {
    match d {
        0 => "DEVICE".into(), 1 => "CLOCK_MONOTONIC".into(), 2 => "CLOCK_MONOTONIC_RAW".into(),
        TIME_DOMAIN_PRESENT_STAGE_LOCAL_EXT => "PRESENT_STAGE_LOCAL".into(), TIME_DOMAIN_SWAPCHAIN_LOCAL_EXT => "SWAPCHAIN_LOCAL".into(),
        _ => format!("time domain {d}"),
    }
}
fn stage_names(bits: u32) -> String { (0..4).filter(|k| bits & 1 << k != 0).map(|k| STAGES[k]).collect::<Vec<_>>().join(", ") }

/// Sets up, takes the display, presents, releases. None for --list.
unsafe fn measure(o: &Opts) -> R<Option<Report>> {
    let entry = ash::Entry::load().map_err(|e| Fail::Error(format!("the Vulkan loader: {e}")))?;
    let offered = entry.enumerate_instance_extension_properties(None).map_err(error("instance extensions"))?;
    let has_i = |n: &CStr| offered.iter().any(|e| e.extension_name_as_c_str() == Ok(n));
    let mut notes = Vec::new();
    let mut inst_exts = vec![khr::surface::NAME, khr::display::NAME];
    if !inst_exts.iter().all(|n| has_i(n)) { return Err(Fail::Error("the Vulkan loader lacks VK_KHR_display".into())); }
    for n in [khr::get_surface_capabilities2::NAME, ext::display_surface_counter::NAME, ext::direct_mode_display::NAME, ext::acquire_drm_display::NAME, ext::headless_surface::NAME] {
        if has_i(n) { inst_exts.push(n) } else { notes.push(format!("instance extension {n:?} not offered")) }
    }
    let on_i = |n: &CStr| inst_exts.contains(&n);
    let names: Vec<_> = inst_exts.iter().map(|n| n.as_ptr()).collect();
    let app = vk::ApplicationInfo::default().api_version(vk::API_VERSION_1_3);
    let instance = entry
        .create_instance(&vk::InstanceCreateInfo::default().application_info(&app).enabled_extension_names(&names), None)
        .map_err(error("vkCreateInstance"))?;
    let gpu = instance.enumerate_physical_devices().unwrap_or_default().into_iter().find(|&g| instance.get_physical_device_properties(g).vendor_id == 0x10de);
    let mut s = Session {
        surface_i: khr::surface::Instance::new(&entry, &instance),
        release_i: on_i(ext::direct_mode_display::NAME).then(|| ext::direct_mode_display::Instance::new(&entry, &instance)),
        _entry: entry.clone(), instance, gpu: gpu.unwrap_or_default(), device: None, swapchain_d: None,
        surface: vk::SurfaceKHR::null(), swapchain: vk::SwapchainKHR::null(), display: vk::DisplayKHR::null(), acquired: false, drm: None,
        pool: vk::CommandPool::null(), buffers: vec![], semaphores: vec![], fences: vec![],
    };
    let Some(gpu) = gpu else { return Err(Fail::Error("no NVIDIA Vulkan device".into())) };
    let props = s.instance.get_physical_device_properties(gpu);
    let v = props.driver_version; // NVIDIA packs it 10.8.8.6 bits
    println!("device: {}, driver {}.{}.{}", CStr::from_ptr(props.device_name.as_ptr()).to_string_lossy(), v >> 22, (v >> 14) & 0xff, (v >> 6) & 0xff);

    // Displays, modes and planes (read-only), and the choice.
    let kd = khr::display::Instance::new(&entry, &s.instance);
    let displays = kd.get_physical_device_display_properties(gpu).map_err(error("display list"))?;
    let name = |d: &vk::DisplayPropertiesKHR| if d.display_name.is_null() { "?".into() } else { CStr::from_ptr(d.display_name).to_string_lossy().into_owned() };
    let mut chosen = None;
    for d in &displays {
        let mut modes = kd.get_display_mode_properties(gpu, d.display).map_err(error("mode list"))?;
        modes.sort_by_key(|m| (std::cmp::Reverse(m.parameters.visible_region.width * m.parameters.visible_region.height), std::cmp::Reverse(m.parameters.refresh_rate)));
        println!("display {}: {}x{} px, {} modes", name(d), d.physical_resolution.width, d.physical_resolution.height, modes.len());
        if o.list {
            for m in &modes { println!("  mode {}x{} @ {:.3} Hz", m.parameters.visible_region.width, m.parameters.visible_region.height, m.parameters.refresh_rate as f64 / 1000.0); }
        }
        if !name(d).contains(&o.display) || chosen.is_some() { continue; }
        let (w, h, hz) = o.mode.unwrap_or((d.physical_resolution.width, d.physical_resolution.height, f64::INFINITY));
        let fits = modes.iter().filter(|m| m.parameters.visible_region.width == w && m.parameters.visible_region.height == h);
        let pick = fits.min_by(|a, b| {
            let off = |m: &&vk::DisplayModePropertiesKHR| if hz.is_finite() { (m.parameters.refresh_rate as f64 / 1000.0 - hz).abs() } else { -(m.parameters.refresh_rate as f64) };
            off(a).total_cmp(&off(b))
        });
        if let Some(m) = pick.filter(|m| !hz.is_finite() || (m.parameters.refresh_rate as f64 / 1000.0 - hz).abs() < 0.5) { chosen = Some((*d, *m)); }
    }
    let Some((d, mode)) = chosen else { return Err(Fail::Error(format!("no display named like {:?} with that mode (--mode {:?})", o.display, o.mode.unwrap_or_default()))) };
    s.display = d.display;
    let planes = kd.get_physical_device_display_plane_properties(gpu).map_err(error("plane list"))?;
    let mut plane: Option<(u32, bool)> = None;
    for (i, p) in planes.iter().enumerate() {
        let on = kd.get_display_plane_supported_displays(gpu, i as u32).unwrap_or_default();
        if o.list { println!("plane {i}: stack index {}, currently on {:?}, can show {:?}", p.current_stack_index, p.current_display, on); }
        let free = [vk::DisplayKHR::null(), d.display].contains(&p.current_display);
        if on.contains(&d.display) && (plane.is_none() || free && !plane.unwrap().1) { plane = Some((i as u32, free)); }
    }
    let Some((plane, _)) = plane else { return Err(Fail::Error("no display plane for the chosen display".into())) };
    let pc = kd.get_display_plane_capabilities(gpu, mode.display_mode, plane).map_err(error("plane capabilities"))?;
    let alpha = [vk::DisplayPlaneAlphaFlagsKHR::OPAQUE, vk::DisplayPlaneAlphaFlagsKHR::GLOBAL, vk::DisplayPlaneAlphaFlagsKHR::PER_PIXEL, vk::DisplayPlaneAlphaFlagsKHR::PER_PIXEL_PREMULTIPLIED]
        .into_iter().find(|&a| pc.supported_alpha.contains(a)).unwrap_or(vk::DisplayPlaneAlphaFlagsKHR::OPAQUE);
    let hz = mode.parameters.refresh_rate as f64 / 1000.0;
    let (w, h) = (mode.parameters.visible_region.width, mode.parameters.visible_region.height);
    println!("chosen: {} at {w}x{h} @ {hz:.3} Hz, plane {plane} (stack index {}, alpha {alpha:?}, dst extent up to {}x{})",
        name(&d), planes[plane as usize].current_stack_index, pc.max_dst_extent.width, pc.max_dst_extent.height);
    let max_frames = (MAX_RUN_S * hz) as usize;
    if o.frames > max_frames { return Err(Fail::Error(format!("--frames {} needs {:.1} s at {hz:.3} Hz; at most {max_frames} ({MAX_RUN_S} s)", o.frames, o.frames as f64 / hz))); }

    // --headless (a test) runs on the integrated GPU, which drives no display: NVIDIA cannot present off-screen.
    let gpu = if !o.headless { gpu } else {
        let all = s.instance.enumerate_physical_devices().unwrap_or_default();
        let igpu = all.into_iter().find(|&g| s.instance.get_physical_device_properties(g).device_type == vk::PhysicalDeviceType::INTEGRATED_GPU);
        s.gpu = igpu.ok_or(Fail::Error("--headless: no integrated GPU".into()))?;
        println!("--headless: off-screen, on {}", CStr::from_ptr(s.instance.get_physical_device_properties(s.gpu).device_name.as_ptr()).to_string_lossy());
        s.gpu
    };
    // The device, with what it offers of the timing extensions.
    let offered = s.instance.enumerate_device_extension_properties(gpu).map_err(error("device extensions"))?;
    let has_d = |n: &CStr| offered.iter().any(|e| e.extension_name_as_c_str() == Ok(n));
    let mut dev_exts = vec![khr::swapchain::NAME];
    if !has_d(khr::swapchain::NAME) { return Err(Fail::Error("no VK_KHR_swapchain".into())); }
    let want_timing = has_d(EXT_PRESENT_TIMING_NAME) && has_d(KHR_PRESENT_ID2_NAME) && has_d(khr::calibrated_timestamps::NAME) && on_i(khr::get_surface_capabilities2::NAME);
    for (n, ok) in [
        (KHR_PRESENT_ID2_NAME, on_i(khr::get_surface_capabilities2::NAME)),
        (khr::calibrated_timestamps::NAME, true),
        (EXT_PRESENT_TIMING_NAME, want_timing),
        (ext::display_control::NAME, on_i(ext::display_surface_counter::NAME)),
    ] {
        if has_d(n) && ok { dev_exts.push(n) } else { notes.push(format!("device extension {n:?} not usable (offered: {})", has_d(n))) }
    }
    let on_d = |n: &CStr| dev_exts.contains(&n);
    let mut f_timing: PhysicalDevicePresentTimingFeaturesEXT = new(ST_PHYSICAL_DEVICE_PRESENT_TIMING_FEATURES_EXT);
    let mut f_id2: PhysicalDevicePresentId2FeaturesKHR = new(ST_PHYSICAL_DEVICE_PRESENT_ID_2_FEATURES_KHR);
    let mut chain: *mut c_void = std::ptr::null_mut();
    if on_d(KHR_PRESENT_ID2_NAME) { f_id2.p_next = chain; chain = &mut f_id2 as *mut _ as *mut c_void; }
    if on_d(EXT_PRESENT_TIMING_NAME) { f_timing.p_next = chain; chain = &mut f_timing as *mut _ as *mut c_void; }
    let mut f2 = vk::PhysicalDeviceFeatures2::default();
    f2.p_next = chain;
    s.instance.get_physical_device_features2(gpu, &mut f2);
    println!("features: presentTiming {}, presentAtAbsoluteTime {}, presentAtRelativeTime {}, presentId2 {}",
        f_timing.present_timing, f_timing.present_at_absolute_time, f_timing.present_at_relative_time, f_id2.present_id2);
    (f_timing.present_at_absolute_time, f_timing.present_at_relative_time) = (0, 0); // only feedback is used, no scheduling
    let family = s.instance.get_physical_device_queue_family_properties(gpu).iter()
        .position(|q| q.queue_flags.contains(vk::QueueFlags::GRAPHICS)).ok_or(Fail::Error("no graphics queue".into()))? as u32;
    let qi = [vk::DeviceQueueCreateInfo::default().queue_family_index(family).queue_priorities(&[1.0])];
    let dn: Vec<_> = dev_exts.iter().map(|n| n.as_ptr()).collect();
    let mut dci = vk::DeviceCreateInfo::default().queue_create_infos(&qi).enabled_extension_names(&dn);
    dci.p_next = chain;
    let device = s.instance.create_device(gpu, &dci, None).map_err(error("vkCreateDevice"))?;
    s.device = Some(device.clone());
    let queue = device.get_device_queue(family, 0);
    let timing_fns = if on_d(EXT_PRESENT_TIMING_NAME) && f_timing.present_timing != 0 { PresentTiming::load(&s.instance, device.handle()) } else { None };
    let calibrate_d = on_d(khr::calibrated_timestamps::NAME).then(|| khr::calibrated_timestamps::Device::new(&s.instance, &device));
    let control_d = on_d(ext::display_control::NAME).then(|| ext::display_control::Device::new(&s.instance, &device));
    s.swapchain_d = Some(khr::swapchain::Device::new(&s.instance, &device));
    println!("device extensions enabled: {}", dev_exts.iter().map(|n| n.to_string_lossy()).collect::<Vec<_>>().join(", "));
    if let Ok(td) = khr::calibrated_timestamps::Instance::new(&entry, &s.instance).get_physical_device_calibrateable_time_domains(gpu) {
        println!("calibrateable time domains: {}", td.iter().map(|t| domain_name(t.as_raw())).collect::<Vec<_>>().join(", "));
    }
    notes.iter().for_each(|n| println!("note: {n}"));
    if o.list {
        println!("--list: stopping here, before taking the display; nothing was taken.");
        return Ok(None);
    }
    if o.hold_ms > 0 {
        println!("holding {} ms before taking the display (test option)", o.hold_ms);
        let until = now() + o.hold_ms * 1_000_000;
        while now() < until { stop_requested()?; std::thread::sleep(Duration::from_millis(10)); }
    }
    stop_requested()?;

    // Take the display: a display-plane surface; if refused, acquire it through DRM and retry.
    let surface_info = (&kd, mode, plane, planes[plane as usize].current_stack_index, alpha, family, f_id2.present_id2 != 0, o.headless);
    let mut sc = match take(&mut s, &entry, surface_info, timing_fns.is_some(), control_d.is_some()) {
        Err(Fail::Refused(first)) if on_i(ext::acquire_drm_display::NAME) && !o.headless => {
            let node = drm_node(&s.instance, gpu).ok_or_else(|| Fail::Refused(format!("{first}; no DRM node to acquire it through")))?;
            let r = ext::acquire_drm_display::Instance::new(&entry, &s.instance).acquire_drm_display(gpu, std::os::fd::AsRawFd::as_raw_fd(&node), d.display);
            s.drm = Some(node);
            r.map_err(|e| Fail::Refused(format!("{first}; vkAcquireDrmDisplayEXT: {e:?}")))?;
            s.acquired = true;
            notes.push(format!("display-plane surface refused ({first}); took the display with vkAcquireDrmDisplayEXT"));
            take(&mut s, &entry, surface_info, timing_fns.is_some(), control_d.is_some()).map_err(|e| match e { Fail::Refused(m) => Fail::Refused(format!("{first}; after vkAcquireDrmDisplayEXT: {m}")), e => e })?
        }
        r => r?,
    };
    // From here on the display is ours: no printing until it is released.
    notes.append(&mut sc.notes);
    let images = s.swapchain_d.as_ref().unwrap().get_swapchain_images(s.swapchain).map_err(error("swapchain images"))?;
    let mut header = vec![
        format!("display: {}, mode {w}x{h} @ {hz:.3} Hz (nominal period {:.6} ms), plane {plane}", name(&d), 1e3 / hz),
        format!("path: {}", if o.headless { "headless surface (test option: nothing was shown on the display)" } else if s.acquired { "display-plane surface, after vkAcquireDrmDisplayEXT" } else { "display-plane surface (no DRM acquire)" }),
        format!("swapchain: {} images, {:?}, FIFO; present timing {}, present id2 {}, vblank counter {}", images.len(), sc.format,
            if sc.timing { "on" } else { "off" }, if sc.ids { "on" } else { "off" }, if sc.counter { "on" } else { "off" }),
    ];

    // Present timing: time domains, the result queue, refresh properties, calibration.
    let mut timing = None;
    if let (true, Some(t)) = (sc.timing, &timing_fns) {
        match time_domains(t, device.handle(), s.swapchain) {
            Err(r) => notes.push(format!("vkGetSwapchainTimeDomainPropertiesEXT: {r:?}; timing off")),
            Ok(list) => {
                header.push(format!("swapchain time domains: {}", list.iter().map(|&(d, id)| format!("{} (id {id})", domain_name(d))).collect::<Vec<_>>().join(", ")));
                let rank = |d: i32| [1, TIME_DOMAIN_SWAPCHAIN_LOCAL_EXT, TIME_DOMAIN_PRESENT_STAGE_LOCAL_EXT].iter().position(|&x| x == d).unwrap_or(9);
                let r = (t.set_queue_size)(device.handle(), s.swapchain, TIMING_QUEUE);
                match list.iter().min_by_key(|&&(d, _)| rank(d)) {
                    Some(&dom) if r == vk::Result::SUCCESS => timing = Some(dom),
                    _ => notes.push(format!("no usable time domain, or vkSetSwapchainPresentTimingQueueSizeEXT({TIMING_QUEUE}): {r:?}; timing off")),
                }
            }
        }
    }
    let queries = if timing.is_some() { sc.stages } else { 0 };
    let refresh = |notes: &mut Vec<String>| {
        let t = timing_fns.as_ref()?;
        let mut p: SwapchainTimingPropertiesEXT = new(ST_SWAPCHAIN_TIMING_PROPERTIES_EXT);
        let r = (t.timing_properties)(device.handle(), s.swapchain, &mut p, std::ptr::null_mut());
        if r != vk::Result::SUCCESS { notes.push(format!("vkGetSwapchainTimingPropertiesEXT: {r:?}")); return None; }
        Some((p.refresh_duration, p.refresh_interval))
    };
    let calibrate = |when: &str, notes: &mut Vec<String>| -> Calib {
        let (Some((dom, id)), Some(c)) = (timing, &calibrate_d) else { return Calib::default() };
        if dom == 1 { return Calib { ok: true, ..Default::default() } } // already CLOCK_MONOTONIC
        let ks: Vec<usize> = (0..4).filter(|k| queries & 1 << k != 0).collect();
        let mut sci = [new::<SwapchainCalibratedTimestampInfoEXT>(ST_SWAPCHAIN_CALIBRATED_TIMESTAMP_INFO_EXT); 4];
        let mut infos = vec![vk::CalibratedTimestampInfoKHR::default().time_domain(vk::TimeDomainKHR::CLOCK_MONOTONIC)];
        for (j, &k) in ks.iter().enumerate() {
            sci[j].swapchain = s.swapchain;
            sci[j].time_domain_id = id;
            sci[j].present_stage = if dom == TIME_DOMAIN_PRESENT_STAGE_LOCAL_EXT { 1 << k } else { 0 };
            let mut info = vk::CalibratedTimestampInfoKHR::default().time_domain(vk::TimeDomainKHR::from_raw(dom));
            if dom == TIME_DOMAIN_PRESENT_STAGE_LOCAL_EXT || dom == TIME_DOMAIN_SWAPCHAIN_LOCAL_EXT { info.p_next = &sci[j] as *const _ as *const c_void; }
            infos.push(info);
        }
        match c.get_calibrated_timestamps(&infos) {
            Ok((ts, dev)) => {
                let mut cal = Calib { ok: ts[1..].iter().all(|&t| t != 0), mono: ts[0], dev, ..Default::default() };
                ks.iter().enumerate().for_each(|(j, &k)| cal.dom[k] = ts[j + 1]);
                if !cal.ok { notes.push(format!("calibration at {when}: the driver returned 0 for the swapchain domain")); }
                cal
            }
            Err(r) => { notes.push(format!("vkGetCalibratedTimestampsKHR at {when}: {r:?}")); Calib::default() }
        }
    };
    let refresh_start = refresh(&mut notes);
    let calib_start = calibrate("start", &mut notes);

    // Draw: per image, two pre-recorded command buffers (square black, square white).
    let gray = if format!("{:?}", sc.format).contains("SRGB") { ((GRAY + 0.055) / 1.055).powf(2.4) } else { GRAY };
    for fill in [0x00u8, 0xff] { s.buffers.push(square_buffer(&s.instance, gpu, &device, fill)?); }
    s.pool = device.create_command_pool(&vk::CommandPoolCreateInfo::default().queue_family_index(family), None).map_err(error("command pool"))?;
    let cmds = device.allocate_command_buffers(&vk::CommandBufferAllocateInfo::default().command_pool(s.pool).command_buffer_count(2 * images.len() as u32))
        .map_err(error("command buffers"))?;
    for (i, &image) in images.iter().enumerate() {
        for white in 0..2 { record(&device, cmds[2 * i + white], image, s.buffers[white].0, gray, sc.extent)?; }
    }
    for _ in 0..IN_FLIGHT + images.len() { s.semaphores.push(device.create_semaphore(&Default::default(), None).map_err(error("semaphore"))?); }
    for _ in 0..IN_FLIGHT { s.fences.push(device.create_fence(&vk::FenceCreateInfo::default().flags(vk::FenceCreateFlags::SIGNALED), None).map_err(error("fence"))?); }
    let (acquired_sem, rendered_sem) = s.semaphores.split_at(IN_FLIGHT);

    // The run. Nothing below allocates per frame except on error paths.
    let swapchain_d = s.swapchain_d.as_ref().unwrap();
    let mut frames: Vec<Frame> = Vec::with_capacity(o.frames);
    let mut drain = Drain::new();
    let (mut presented, mut counter_ok, mut ask, mut draining) = (0usize, sc.counter, timing.is_some(), timing.is_some());
    let t_start = now();
    'run: for i in 0..o.frames {
        if STOP.load(SeqCst) != 0 { break; }
        let slot = i % IN_FLIGHT;
        let mut waits = 0;
        while let Err(r) = device.wait_for_fences(&[s.fences[slot]], true, 1_000_000_000) {
            waits += 1;
            if STOP.load(SeqCst) != 0 { break 'run; }
            if r != vk::Result::TIMEOUT || waits > 5 { notes.push(format!("frame {i}: fence wait: {r:?}")); break 'run; }
        }
        let mut tries = 0;
        let image = loop {
            match swapchain_d.acquire_next_image(s.swapchain, 1_000_000_000, acquired_sem[slot], vk::Fence::null()) {
                Ok((image, _)) => break image,
                Err(_) if STOP.load(SeqCst) != 0 => break 'run,
                Err(vk::Result::TIMEOUT | vk::Result::NOT_READY) if tries < 3 => tries += 1,
                Err(r) if presented == 0 => return Err(Fail::Refused(format!("vkAcquireNextImageKHR: {r:?}"))),
                Err(r) => { notes.push(format!("frame {i}: vkAcquireNextImageKHR: {r:?}")); break 'run; }
            }
        };
        let _ = device.reset_fences(&[s.fences[slot]]);
        let (wait, stage, cmd, done) = ([acquired_sem[slot]], [vk::PipelineStageFlags::TRANSFER], [cmds[2 * image as usize + i % 2]], [rendered_sem[image as usize]]);
        let submit = vk::SubmitInfo::default().wait_semaphores(&wait).wait_dst_stage_mask(&stage).command_buffers(&cmd).signal_semaphores(&done);
        if let Err(r) = device.queue_submit(queue, &[submit], s.fences[slot]) { notes.push(format!("frame {i}: vkQueueSubmit: {r:?}")); break; }

        let ids = [i as u64 + 1];
        let mut id2: PresentId2KHR = new(ST_PRESENT_ID_2_KHR);
        (id2.swapchain_count, id2.p_present_ids) = (1, ids.as_ptr());
        let mut ti: PresentTimingInfoEXT = new(ST_PRESENT_TIMING_INFO_EXT);
        (ti.time_domain_id, ti.present_stage_queries) = (timing.map_or(0, |t| t.1), queries);
        let mut tis: PresentTimingsInfoEXT = new(ST_PRESENT_TIMINGS_INFO_EXT);
        (tis.swapchain_count, tis.p_timing_infos) = (1, &ti);
        let mut head: *const c_void = if sc.ids { &id2 as *const _ as _ } else { std::ptr::null() };
        if ask { tis.p_next = head; head = &tis as *const _ as _; }
        let (scs, images_i) = ([s.swapchain], [image]);
        let mut pi = vk::PresentInfoKHR::default().wait_semaphores(&done).swapchains(&scs).image_indices(&images_i);
        pi.p_next = head;
        let t_call = now();
        let r = swapchain_d.queue_present(queue, &pi);
        let t_return = now();
        let result = match r { Ok(false) => 0, Ok(true) => vk::Result::SUBOPTIMAL_KHR.as_raw(), Err(e) => e.as_raw() };
        frames.push(Frame { image, t_call, t_return, result, ..Default::default() });
        match r {
            Ok(_) => presented += 1,
            Err(e) if e.as_raw() == ERROR_PRESENT_TIMING_QUEUE_FULL_EXT => {
                notes.push(format!("frame {i}: timing result queue full; not presented; no timing requested from here on"));
                ask = false;
            }
            Err(e) if presented == 0 => return Err(Fail::Refused(format!("first vkQueuePresentKHR: {e:?}"))),
            Err(e) => { notes.push(format!("frame {i}: vkQueuePresentKHR: {e:?}")); break; }
        }
        if counter_ok && i > images.len() {
            let mut v = 0;
            match (control_d.as_ref().unwrap().fp().get_swapchain_counter_ext)(device.handle(), s.swapchain, vk::SurfaceCounterFlagsEXT::VBLANK, &mut v) {
                vk::Result::SUCCESS => frames[i].vblank = Some(v),
                r => { notes.push(format!("frame {i}: vkGetSwapchainCounterEXT: {r:?}; counter off")); counter_ok = false; }
            }
        }
        if let (Some(t), true) = (&timing_fns, draining) {
            if let Err(r) = drain.run(t, device.handle(), s.swapchain, &mut frames) {
                notes.push(format!("frame {i}: vkGetPastPresentationTimingEXT: {r:?}; timing off from here on"));
                (ask, draining) = (false, false);
            }
        }
    }
    let t_end = now();
    let _ = device.device_wait_idle();
    if let (Some(t), true) = (&timing_fns, draining) {
        let until = now() + 500_000_000; // collect the last results for up to 0.5 s
        while frames.iter().any(|f| f.result >= 0 && !f.got) && now() < until {
            if drain.run(t, device.handle(), s.swapchain, &mut frames).is_err() { break; }
            std::thread::sleep(Duration::from_millis(5));
        }
    }
    let refresh_end = refresh(&mut notes);
    let calib_end = calibrate("end", &mut notes);
    if drain.counters.0 > 1 || drain.counters.1 > 1 { notes.push(format!("timing properties / time domains changed during the run (counters {:?})", drain.counters)); }
    header.push(format!("run: {} of {} frames presented in {:.3} s", presented, o.frames, (t_end - t_start) as f64 / 1e9));
    if refresh_start != refresh_end { header.push(format!("driver refresh at start {refresh_start:?}, at end {refresh_end:?} (ns)")); }
    Ok(Some(Report {
        header, notes, frames, requested: o.frames, nominal_ns: 1e9 / hz, refresh: refresh_end.or(refresh_start),
        domain: timing, queries, calib: [calib_start, calib_end], stopped: STOP.load(SeqCst),
    }))
    // `s` drops here: swapchain, surface and device destroyed, display released.
}

/// What the swapchain was created with.
struct Swapchain { format: vk::Format, extent: vk::Extent2D, timing: bool, ids: bool, counter: bool, stages: u32, notes: Vec<String> }

type SurfaceInfo<'a> = (&'a khr::display::Instance, vk::DisplayModePropertiesKHR, u32, u32, vk::DisplayPlaneAlphaFlagsKHR, u32, bool, bool);

/// Creates the display-plane surface and a FIFO swapchain on it. Any failure is a refusal,
/// with the surface destroyed again.
unsafe fn take(s: &mut Session, entry: &ash::Entry, si: SurfaceInfo, timing: bool, control: bool) -> R<Swapchain> {
    let (kd, mode, plane, stack, alpha, family, id2, headless) = si;
    let info = vk::DisplaySurfaceCreateInfoKHR::default().display_mode(mode.display_mode).plane_index(plane).plane_stack_index(stack)
        .transform(vk::SurfaceTransformFlagsKHR::IDENTITY).global_alpha(1.0).alpha_mode(alpha).image_extent(mode.parameters.visible_region);
    s.surface = if headless {
        ext::headless_surface::Instance::new(entry, &s.instance).create_headless_surface(&vk::HeadlessSurfaceCreateInfoEXT::default(), None)
    } else {
        kd.create_display_plane_surface(&info, None)
    }
    .map_err(|r| Fail::Refused(format!("vkCreate{}SurfaceKHR: {r:?}", if headless { "Headless" } else { "DisplayPlane" })))?;
    let result = swapchain(s, entry, family, timing, control, id2, mode.parameters.visible_region);
    if result.is_err() {
        s.surface_i.destroy_surface(s.surface, None);
        s.surface = vk::SurfaceKHR::null();
    }
    result
}

unsafe fn swapchain(s: &mut Session, entry: &ash::Entry, family: u32, timing: bool, control: bool, id2: bool, want: vk::Extent2D) -> R<Swapchain> {
    let refused = |what: &'static str| move |r: vk::Result| Fail::Refused(format!("{what}: {r:?}"));
    if !s.surface_i.get_physical_device_surface_support(s.gpu, family, s.surface).map_err(refused("vkGetPhysicalDeviceSurfaceSupportKHR"))? {
        return Err(Fail::Refused("the queue cannot present to the display surface".into()));
    }
    let mut notes = Vec::new();
    let mut pt: PresentTimingSurfaceCapabilitiesEXT = new(ST_PRESENT_TIMING_SURFACE_CAPABILITIES_EXT);
    let mut pid2: SurfaceCapabilitiesPresentId2KHR = new(ST_SURFACE_CAPABILITIES_PRESENT_ID_2_KHR);
    let mut caps2 = vk::SurfaceCapabilities2KHR::default();
    if id2 { pid2.p_next = caps2.p_next; caps2.p_next = &mut pid2 as *mut _ as *mut c_void; }
    if timing { pt.p_next = caps2.p_next; caps2.p_next = &mut pt as *mut _ as *mut c_void; }
    let caps = if id2 || timing {
        let sinfo = vk::PhysicalDeviceSurfaceInfo2KHR::default().surface(s.surface);
        khr::get_surface_capabilities2::Instance::new(entry, &s.instance).get_physical_device_surface_capabilities2(s.gpu, &sinfo, &mut caps2)
            .map_err(refused("vkGetPhysicalDeviceSurfaceCapabilities2KHR"))?;
        caps2.surface_capabilities
    } else {
        s.surface_i.get_physical_device_surface_capabilities(s.gpu, s.surface).map_err(refused("vkGetPhysicalDeviceSurfaceCapabilitiesKHR"))?
    };
    let timing = timing && pt.present_timing_supported != 0;
    let ids = id2 && pid2.present_id2_supported != 0;
    if timing && !ids { notes.push("present timing without present ids: results cannot be matched to frames".into()); }
    let mut counter = false;
    if control {
        let mut c2 = vk::SurfaceCapabilities2EXT::default();
        let r = (ext::display_surface_counter::Instance::new(entry, &s.instance).fp().get_physical_device_surface_capabilities2_ext)(s.gpu, s.surface, &mut c2);
        counter = r == vk::Result::SUCCESS && c2.supported_surface_counters.contains(vk::SurfaceCounterFlagsEXT::VBLANK);
        if !counter { notes.push(format!("vblank counter not available ({r:?}, counters {:?})", c2.supported_surface_counters)); }
    }
    if !caps.supported_usage_flags.contains(vk::ImageUsageFlags::TRANSFER_DST) { return Err(Fail::Error("display surface images cannot be written by transfers".into())); }
    let formats = s.surface_i.get_physical_device_surface_formats(s.gpu, s.surface).map_err(refused("vkGetPhysicalDeviceSurfaceFormatsKHR"))?;
    let four_bytes = [vk::Format::B8G8R8A8_UNORM, vk::Format::R8G8B8A8_UNORM, vk::Format::A8B8G8R8_UNORM_PACK32, vk::Format::A2R10G10B10_UNORM_PACK32,
        vk::Format::A2B10G10R10_UNORM_PACK32, vk::Format::B8G8R8A8_SRGB, vk::Format::R8G8B8A8_SRGB, vk::Format::A8B8G8R8_SRGB_PACK32];
    let format = four_bytes.iter().find_map(|f| formats.iter().find(|sf| sf.format == *f))
        .ok_or_else(|| Fail::Error(format!("no 32-bit surface format among {formats:?}")))?;
    let extent = if caps.current_extent.width != u32::MAX { caps.current_extent } else { want };
    let count = if caps.max_image_count > 0 { 3.max(caps.min_image_count).min(caps.max_image_count) } else { 3.max(caps.min_image_count) };
    let composite = [vk::CompositeAlphaFlagsKHR::OPAQUE, vk::CompositeAlphaFlagsKHR::INHERIT, vk::CompositeAlphaFlagsKHR::PRE_MULTIPLIED, vk::CompositeAlphaFlagsKHR::POST_MULTIPLIED]
        .into_iter().find(|&a| caps.supported_composite_alpha.contains(a)).unwrap_or(vk::CompositeAlphaFlagsKHR::OPAQUE);
    // Printed before the swapchain exists, i.e. before the display is taken.
    let surf = format!("surface: presentTimingSupported {}, stages {:#x} ({}), presentId2Supported {}, vblank counter {counter}, {:?} (of {} formats), images {}..{}",
        pt.present_timing_supported, pt.present_stage_queries, stage_names(pt.present_stage_queries), pid2.present_id2_supported,
        format.format, formats.len(), caps.min_image_count, caps.max_image_count);
    println!("{surf}");
    notes.push(surf);
    let counters = vk::SwapchainCounterCreateInfoEXT::default().surface_counters(vk::SurfaceCounterFlagsEXT::VBLANK);
    let sd = s.swapchain_d.as_ref().unwrap();
    let attempt = |timing: bool, ids: bool, counter: bool| {
        let flags = if timing { SWAPCHAIN_CREATE_PRESENT_TIMING_BIT_EXT } else { 0 } | if ids { SWAPCHAIN_CREATE_PRESENT_ID_2_BIT_KHR } else { 0 };
        let mut ci = vk::SwapchainCreateInfoKHR::default().flags(vk::SwapchainCreateFlagsKHR::from_raw(flags)).surface(s.surface).min_image_count(count)
            .image_format(format.format).image_color_space(format.color_space).image_extent(extent).image_array_layers(1)
            .image_usage(vk::ImageUsageFlags::TRANSFER_DST).image_sharing_mode(vk::SharingMode::EXCLUSIVE).pre_transform(caps.current_transform)
            .composite_alpha(composite).present_mode(vk::PresentModeKHR::FIFO).clipped(true);
        if counter { ci.p_next = &counters as *const _ as *const c_void; }
        sd.create_swapchain(&ci, None)
    };
    let (mut timing, mut ids, mut counter) = (timing, ids, counter);
    s.swapchain = match attempt(timing, ids, counter) {
        Ok(sc) => sc,
        Err(first) if timing || ids || counter => {
            let sc = attempt(false, false, false).map_err(|r| Fail::Refused(format!("vkCreateSwapchainKHR: {first:?}, and without timing: {r:?}")))?;
            notes.push(format!("swapchain with present timing / present id2 / vblank counter refused ({first:?}); created without them"));
            (timing, ids, counter) = (false, false, false);
            sc
        }
        Err(r) => return Err(Fail::Refused(format!("vkCreateSwapchainKHR: {r:?}"))),
    };
    Ok(Swapchain { format: format.format, extent, timing, ids, counter, stages: if timing { pt.present_stage_queries } else { 0 }, notes })
}

/// The swapchain's time domains and their ids (two-call idiom).
unsafe fn time_domains(t: &PresentTiming, device: vk::Device, sc: vk::SwapchainKHR) -> Result<Vec<(i32, u64)>, vk::Result> {
    let mut p: SwapchainTimeDomainPropertiesEXT = new(ST_SWAPCHAIN_TIME_DOMAIN_PROPERTIES_EXT);
    let r = (t.time_domains)(device, sc, &mut p, std::ptr::null_mut());
    if r != vk::Result::SUCCESS { return Err(r); }
    let (mut domains, mut ids) = (vec![vk::TimeDomainKHR::DEVICE; p.time_domain_count as usize], vec![0u64; p.time_domain_count as usize]);
    (p.p_time_domains, p.p_time_domain_ids) = (domains.as_mut_ptr(), ids.as_mut_ptr());
    let r = (t.time_domains)(device, sc, &mut p, std::ptr::null_mut());
    if r != vk::Result::SUCCESS { return Err(r); }
    Ok(domains.iter().zip(&ids).take(p.time_domain_count as usize).map(|(d, &id)| (d.as_raw(), id)).collect())
}

/// Preallocated space for vkGetPastPresentationTimingEXT results.
struct Drain { buf: Vec<PastPresentationTimingEXT>, stages: Vec<PresentStageTimeEXT>, counters: (u64, u64) }

impl Drain {
    fn new() -> Self { Drain { buf: vec![new(ST_PAST_PRESENTATION_TIMING_EXT); BATCH], stages: vec![Default::default(); 4 * BATCH], counters: (0, 0) } }

    /// Moves every available complete result into `frames` (indexed by present id - 1).
    unsafe fn run(&mut self, t: &PresentTiming, device: vk::Device, sc: vk::SwapchainKHR, frames: &mut [Frame]) -> Result<(), vk::Result> {
        let mut info: PastPresentationTimingInfoEXT = new(ST_PAST_PRESENTATION_TIMING_INFO_EXT);
        info.swapchain = sc;
        loop {
            for (k, b) in self.buf.iter_mut().enumerate() {
                (b.present_stage_count, b.p_present_stages) = (4, self.stages.as_mut_ptr().add(4 * k));
            }
            let mut p: PastPresentationTimingPropertiesEXT = new(ST_PAST_PRESENTATION_TIMING_PROPERTIES_EXT);
            (p.presentation_timing_count, p.p_presentation_timings) = (BATCH as u32, self.buf.as_mut_ptr());
            let r = (t.past)(device, &info, &mut p);
            if r != vk::Result::SUCCESS && r != vk::Result::INCOMPLETE { return Err(r); }
            self.counters = (self.counters.0.max(p.timing_properties_counter), self.counters.1.max(p.time_domains_counter));
            for (k, b) in self.buf.iter().take(p.presentation_timing_count as usize).enumerate() {
                let Some(f) = frames.get_mut((b.present_id as usize).wrapping_sub(1)) else { continue };
                (f.got, f.complete, f.domain, f.domain_id) = (true, b.report_complete != 0, b.time_domain.as_raw(), b.time_domain_id);
                for st in &self.stages[4 * k..4 * k + b.present_stage_count.min(4) as usize] {
                    if st.stage.is_power_of_two() && st.stage < 16 { f.stage[st.stage.trailing_zeros() as usize] = st.time; }
                }
            }
            if r == vk::Result::SUCCESS { return Ok(()); }
        }
    }
}

/// A host-visible buffer of SQUARE x SQUARE 4-byte pixels, every byte `fill`.
unsafe fn square_buffer(instance: &ash::Instance, gpu: vk::PhysicalDevice, device: &ash::Device, fill: u8) -> R<(vk::Buffer, vk::DeviceMemory)> {
    let size = (SQUARE * SQUARE * 4) as u64;
    let buffer = device.create_buffer(&vk::BufferCreateInfo::default().size(size).usage(vk::BufferUsageFlags::TRANSFER_SRC), None).map_err(error("buffer"))?;
    let need = device.get_buffer_memory_requirements(buffer);
    let types = instance.get_physical_device_memory_properties(gpu);
    let host = vk::MemoryPropertyFlags::HOST_VISIBLE | vk::MemoryPropertyFlags::HOST_COHERENT;
    let index = (0..types.memory_type_count)
        .find(|&i| need.memory_type_bits & (1 << i) != 0 && types.memory_types[i as usize].property_flags.contains(host))
        .ok_or(Fail::Error("no host-visible memory".into()))?;
    let memory = device.allocate_memory(&vk::MemoryAllocateInfo::default().allocation_size(need.size).memory_type_index(index), None).map_err(error("memory"))?;
    device.bind_buffer_memory(buffer, memory, 0).map_err(error("bind"))?;
    let p = device.map_memory(memory, 0, size, vk::MemoryMapFlags::empty()).map_err(error("map"))? as *mut u8;
    std::ptr::write_bytes(p, fill, size as usize);
    device.unmap_memory(memory);
    Ok((buffer, memory))
}

/// Clears `image` to the gray field and copies the square into its bottom-left corner.
unsafe fn record(device: &ash::Device, cmd: vk::CommandBuffer, image: vk::Image, square: vk::Buffer, gray: f32, extent: vk::Extent2D) -> R<()> {
    let range = vk::ImageSubresourceRange { aspect_mask: vk::ImageAspectFlags::COLOR, base_mip_level: 0, level_count: 1, base_array_layer: 0, layer_count: 1 };
    let barrier = |old, new, src: vk::AccessFlags, dst: vk::AccessFlags| vk::ImageMemoryBarrier::default().image(image).old_layout(old).new_layout(new)
        .src_access_mask(src).dst_access_mask(dst).subresource_range(range)
        .src_queue_family_index(vk::QUEUE_FAMILY_IGNORED).dst_queue_family_index(vk::QUEUE_FAMILY_IGNORED);
    let (dst, write) = (vk::ImageLayout::TRANSFER_DST_OPTIMAL, vk::AccessFlags::TRANSFER_WRITE);
    let transfer = vk::PipelineStageFlags::TRANSFER;
    device.begin_command_buffer(cmd, &vk::CommandBufferBeginInfo::default().flags(vk::CommandBufferUsageFlags::SIMULTANEOUS_USE)).map_err(error("begin"))?;
    device.cmd_pipeline_barrier(cmd, transfer, transfer, vk::DependencyFlags::empty(), &[], &[], &[barrier(vk::ImageLayout::UNDEFINED, dst, vk::AccessFlags::empty(), write)]);
    device.cmd_clear_color_image(cmd, image, dst, &vk::ClearColorValue { float32: [gray, gray, gray, 1.0] }, &[range]);
    device.cmd_pipeline_barrier(cmd, transfer, transfer, vk::DependencyFlags::empty(), &[], &[], &[barrier(dst, dst, write, write)]);
    let region = vk::BufferImageCopy {
        buffer_offset: 0, buffer_row_length: 0, buffer_image_height: 0,
        image_subresource: vk::ImageSubresourceLayers { aspect_mask: vk::ImageAspectFlags::COLOR, mip_level: 0, base_array_layer: 0, layer_count: 1 },
        image_offset: vk::Offset3D { x: 0, y: (extent.height - SQUARE) as i32, z: 0 },
        image_extent: vk::Extent3D { width: SQUARE, height: SQUARE, depth: 1 },
    };
    device.cmd_copy_buffer_to_image(cmd, square, image, dst, &[region]);
    let present = barrier(dst, vk::ImageLayout::PRESENT_SRC_KHR, write, vk::AccessFlags::empty());
    device.cmd_pipeline_barrier(cmd, transfer, vk::PipelineStageFlags::BOTTOM_OF_PIPE, vk::DependencyFlags::empty(), &[], &[], &[present]);
    device.end_command_buffer(cmd).map_err(error("end"))
}

/// The NVIDIA device's DRM primary node (VK_EXT_physical_device_drm), opened read-write.
unsafe fn drm_node(instance: &ash::Instance, gpu: vk::PhysicalDevice) -> Option<std::fs::File> {
    use std::os::unix::fs::MetadataExt;
    let mut drm = vk::PhysicalDeviceDrmPropertiesEXT::default();
    let mut p2 = vk::PhysicalDeviceProperties2::default().push_next(&mut drm);
    instance.get_physical_device_properties2(gpu, &mut p2);
    if drm.has_primary == 0 { return None; }
    let file = std::fs::OpenOptions::new().read(true).write(true).open(format!("/dev/dri/card{}", drm.primary_minor)).ok()?;
    let (ma, mi) = (drm.primary_major as u64, drm.primary_minor as u64);
    let dev = ((ma & 0xfff) << 8) | ((ma & !0xfff) << 32) | (mi & 0xff) | ((mi & !0xff) << 12); // glibc makedev
    (file.metadata().ok()?.rdev() == dev).then_some(file)
}

fn pct(v: &[f64], p: f64) -> f64 { v[((p / 100.0) * (v.len() - 1) as f64).round() as usize] }
fn dist(mut v: Vec<f64>) -> String {
    if v.is_empty() { return "none".into(); }
    v.sort_by(f64::total_cmp);
    format!("n {}, median {:.4}, min {:.4}, max {:.4}, p1 {:.4}, p5 {:.4}, p95 {:.4}, p99 {:.4}",
        v.len(), pct(&v, 50.0), v[0], v[v.len() - 1], pct(&v, 1.0), pct(&v, 5.0), pct(&v, 95.0), pct(&v, 99.0))
}

/// UTC as YYYYMMDDTHHMMSSZ (civil-from-days, H. Hinnant).
fn utc_stamp() -> String {
    let t = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map_or(0, |d| d.as_secs() as i64);
    let (z, rem) = (t.div_euclid(86400) + 719468, t.rem_euclid(86400));
    let (era, doe) = (z.div_euclid(146097), z.rem_euclid(146097));
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let (d, m) = (doy - (153 * mp + 2) / 5 + 1, if mp < 10 { mp + 3 } else { mp - 9 });
    format!("{:04}{m:02}{d:02}T{:02}{:02}{:02}Z", yoe + era * 400 + (m <= 2) as i64, rem / 3600, rem / 60 % 60, rem % 60)
}

/// The CSV and the summary lines.
fn summarize(r: &Report) -> (String, Vec<String>) {
    let f = &r.frames;
    // Stage time in CLOCK_MONOTONIC, if the result's domain is that or the calibrated one.
    let cal = if r.calib[0].ok { r.calib[0] } else { r.calib[1] };
    let mono = |fr: &Frame, k: usize| -> Option<u64> {
        let t = fr.stage[k];
        if t == 0 { return None; }
        if fr.domain == 1 { return Some(t); }
        (cal.ok && r.domain == Some((fr.domain, fr.domain_id))).then(|| (t as i64 + cal.offset(k)) as u64)
    };
    let mut csv = String::from("frame,present_id,image,square,cpu_present_call_ns,cpu_present_return_ns,present_result,vblank_counter,timing_result,report_complete,time_domain,time_domain_id");
    for k in STAGES { write!(csv, ",{}_ns", k.to_lowercase()).unwrap(); }
    for k in STAGES { write!(csv, ",{}_monotonic_ns", k.to_lowercase()).unwrap(); }
    csv.push('\n');
    let opt = |v: Option<u64>| v.map_or(String::new(), |v| v.to_string());
    for (i, fr) in f.iter().enumerate() {
        write!(csv, "{i},{},{},{},{},{},{},{},{},{},{},{}", i + 1, fr.image, ["black", "white"][i % 2], fr.t_call, fr.t_return, fr.result, opt(fr.vblank),
            fr.got as u8, fr.complete as u8, if fr.got { domain_name(fr.domain) } else { String::new() }, if fr.got { fr.domain_id.to_string() } else { String::new() }).unwrap();
        for k in 0..4 { write!(csv, ",{}", if fr.got && r.queries & 1 << k != 0 { fr.stage[k].to_string() } else { String::new() }).unwrap(); }
        for k in 0..4 { write!(csv, ",{}", opt(mono(fr, k))).unwrap(); }
        csv.push('\n');
    }

    let mut s = r.header.clone();
    let period = match r.refresh {
        Some((d, i)) if d > 0 => { s.push(format!("driver refresh: refreshDuration {d} ns, refreshInterval {i} ns ({})", if i == d { "fixed rate" } else if i == u64::MAX { "VRR" } else { "?" })); d as f64 }
        _ => { s.push(format!("driver refresh: not reported; using the mode's nominal period {:.0} ns", r.nominal_ns)); r.nominal_ns }
    };
    let counts: Vec<usize> = (0..4).map(|k| f.iter().filter(|fr| fr.stage[k] != 0).count()).collect();
    let primary = (0..4).rev().find(|&k| counts[k] > 0);
    match r.domain {
        None => s.push("present timing: off (see notes); intervals below are of CPU present calls only".into()),
        Some((d, id)) => {
            s.push(format!("time domain: {} (id {id}){}", domain_name(d), if d == 1 { String::new() } else if cal.ok {
                format!(", calibrated to CLOCK_MONOTONIC: offset {} ns (max deviation {} ns){}", cal.offset(primary.unwrap_or(0)), cal.dev,
                    if r.calib[0].ok && r.calib[1].ok { format!(", drift over the run {} ns", r.calib[1].offset(primary.unwrap_or(0)) - r.calib[0].offset(primary.unwrap_or(0))) } else { String::new() })
            } else { ", not calibrated".into() }));
            s.push(format!("stages requested: {}; frames with a nonzero time: {}", stage_names(r.queries),
                (0..4).filter(|k| r.queries & 1 << k != 0).map(|k| format!("{} {}", STAGES[k], counts[k])).collect::<Vec<_>>().join(", ")));
            s.push(format!("timing results: {} of {} frames ({} complete)", f.iter().filter(|x| x.got).count(), f.len(), f.iter().filter(|x| x.complete).count()));
        }
    }
    let ms = |a: u64, b: u64| (b as f64 - a as f64) / 1e6;
    let pairs = || f.windows(2).enumerate();
    if let Some(k) = primary {
        let iv: Vec<(usize, f64)> = pairs().filter(|(_, w)| w[0].stage[k] != 0 && w[1].stage[k] != 0).map(|(i, w)| (i + 1, ms(w[0].stage[k], w[1].stage[k]))).collect();
        s.push(format!("intervals between successive {} times (ms): {}", STAGES[k], dist(iv.iter().map(|x| x.1).collect())));
        let missed: Vec<usize> = iv.iter().filter(|x| x.1 * 1e6 > 1.5 * period).map(|x| x.0).collect();
        s.push(format!("missed (interval > 1.5 periods = {:.3} ms): {}{}", 1.5 * period / 1e6, missed.len(),
            if missed.is_empty() { String::new() } else { format!(", at frames {:?}{}", &missed[..missed.len().min(12)], if missed.len() > 12 { " ..." } else { "" }) }));
        for j in (0..4).filter(|&j| j != k && counts[j] > 1) {
            let v: Vec<f64> = pairs().filter(|(_, w)| w[0].stage[j] != 0 && w[1].stage[j] != 0).map(|(_, w)| ms(w[0].stage[j], w[1].stage[j])).collect();
            s.push(format!("  {} intervals (ms): {}", STAGES[j], dist(v)));
        }
        let lat: Vec<f64> = f.iter().filter_map(|fr| mono(fr, k).map(|t| ms(fr.t_call, t))).collect();
        s.push(format!("CPU present call -> {} (ms): {}", STAGES[k], if lat.is_empty() { "not computable (no calibration)".into() } else { dist(lat) }));
    }
    s.push(format!("CPU present-call intervals (ms): {}", dist(f.windows(2).map(|w| ms(w[0].t_call, w[1].t_call)).collect())));
    let v: Vec<(usize, u64)> = f.iter().enumerate().filter_map(|(i, fr)| fr.vblank.map(|v| (i, v))).collect();
    if let (Some(a), Some(b)) = (v.first(), v.last()) {
        s.push(format!("vblank counter: {} at frame {}, {} at frame {}: {} vblanks over {} frames", a.1, a.0, b.1, b.0, b.1 - a.1, b.0 - a.0));
    }
    if r.stopped != 0 || f.len() < r.requested {
        s.push(format!("stopped early: {} of {} frames{}", f.len(), r.requested, match r.stopped { 0 => String::new(), -1 => " (watchdog)".into(), sig => format!(" (signal {sig})") }));
    }
    s.extend(r.notes.iter().map(|n| format!("note: {n}")));
    (csv, s)
}

/// Writes the CSV and the summary, prints the summary; returns the exit code.
fn report(o: &Opts, r: &Report) -> i32 {
    let ((csv, mut s), code, stamp) = (summarize(r), stop_code(), utc_stamp());
    let base = format!("{}/run-{stamp}", o.out);
    let written = std::fs::create_dir_all(&o.out).and_then(|_| std::fs::write(format!("{base}.csv"), &csv))
        .and_then(|_| std::fs::write(format!("{base}.txt"), format!("timing run {stamp}\n{}\n", s.join("\n"))));
    match &written {
        Ok(()) => s.push(format!("results: {base}.csv and .txt")),
        Err(e) => s.push(format!("could not write results to {}: {e}", o.out)),
    }
    println!("{}", s.join("\n"));
    if written.is_err() { 1 } else if code != 0 { code } else if r.frames.len() < r.requested { 1 } else { 0 }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 1200 synthetic frames at exactly 8.333333 ms in a swapchain-local clock that runs 5 s
    /// behind CLOCK_MONOTONIC; frame 600 is one refresh late; every present call is 20 ms early.
    #[test]
    fn summary_from_known_frames() {
        let (period, offset) = (8_333_333u64, 5_000_000_000i64);
        let frames: Vec<Frame> = (0..1200u64).map(|i| {
            let fpo = 1_000_000_000_000 + (i + (i >= 600) as u64) * period; // swapchain-local
            let mono = (fpo as i64 + offset) as u64;
            let mut stage = [0; 4];
            (stage[0], stage[2]) = (fpo - 3_000_000, fpo);
            Frame { t_call: mono - 20_000_000, t_return: mono - 19_900_000, got: true, complete: true, vblank: Some(500 + i),
                domain: TIME_DOMAIN_SWAPCHAIN_LOCAL_EXT, domain_id: 7, stage, ..Default::default() }
        }).collect();
        let cal = Calib { ok: true, mono: (2_000_000_000 + offset) as u64, dom: [2_000_000_000; 4], dev: 1000 };
        let r = Report { header: vec![], notes: vec![], frames, requested: 1200, nominal_ns: 1e9 / 120.0, refresh: Some((period, period)),
            domain: Some((TIME_DOMAIN_SWAPCHAIN_LOCAL_EXT, 7)), queries: 0b101, calib: [cal, cal], stopped: 0 };
        let (csv, lines) = summarize(&r);
        let all = lines.join("\n");
        println!("{all}");
        assert!(all.contains("intervals between successive IMAGE_FIRST_PIXEL_OUT times (ms): n 1199, median 8.3333, min 8.3333, max 16.6667"));
        assert!(all.contains("missed (interval > 1.5 periods = 12.500 ms): 1, at frames [600]"));
        assert!(all.contains("CPU present call -> IMAGE_FIRST_PIXEL_OUT (ms): n 1200, median 20.0000, min 20.0000, max 20.0000"));
        assert!(all.contains("offset 5000000000 ns (max deviation 1000 ns), drift over the run 0 ns"));
        assert!(all.contains("vblank counter: 500 at frame 0, 1699 at frame 1199: 1199 vblanks over 1199 frames"));
        assert!(!all.contains("stopped early"));
        let rows: Vec<&str> = csv.lines().collect();
        assert_eq!(rows.len(), 1201);
        let row600: Vec<&str> = rows[601].split(',').collect();
        let fpo = 1_000_000_000_000 + 601 * period;
        assert_eq!(row600[14], fpo.to_string()); // image_first_pixel_out_ns
        assert_eq!(row600[18], (fpo as i64 + offset).to_string()); // its CLOCK_MONOTONIC value
        assert_eq!(row600[13], ""); // REQUEST_DEQUEUED was not requested
    }
}
