//! Hand-written FFI for what ash 0.38 (Vulkan headers 1.3.281) lacks: VK_EXT_present_timing
//! (spec revision 3) and VK_KHR_present_id2. Written from the Khronos reference pages; every
//! layout, value, signature and name here is checked at compile time against vk.xml by
//! layout_check.rs, which tools/gen_layout_check.py generates from vk.xml alone.

use ash::vk;
use std::ffi::{CStr, c_void};

pub const EXT_PRESENT_TIMING_NAME: &CStr = c"VK_EXT_present_timing";
pub const KHR_PRESENT_ID2_NAME: &CStr = c"VK_KHR_present_id2";

pub const ST_PHYSICAL_DEVICE_PRESENT_TIMING_FEATURES_EXT: i32 = 1000208000;
pub const ST_SWAPCHAIN_TIMING_PROPERTIES_EXT: i32 = 1000208001;
pub const ST_SWAPCHAIN_TIME_DOMAIN_PROPERTIES_EXT: i32 = 1000208002;
pub const ST_PRESENT_TIMINGS_INFO_EXT: i32 = 1000208003;
pub const ST_PRESENT_TIMING_INFO_EXT: i32 = 1000208004;
pub const ST_PAST_PRESENTATION_TIMING_INFO_EXT: i32 = 1000208005;
pub const ST_PAST_PRESENTATION_TIMING_PROPERTIES_EXT: i32 = 1000208006;
pub const ST_PAST_PRESENTATION_TIMING_EXT: i32 = 1000208007;
pub const ST_PRESENT_TIMING_SURFACE_CAPABILITIES_EXT: i32 = 1000208008;
pub const ST_SWAPCHAIN_CALIBRATED_TIMESTAMP_INFO_EXT: i32 = 1000208009;
pub const ST_SURFACE_CAPABILITIES_PRESENT_ID_2_KHR: i32 = 1000479000;
pub const ST_PRESENT_ID_2_KHR: i32 = 1000479001;
pub const ST_PHYSICAL_DEVICE_PRESENT_ID_2_FEATURES_KHR: i32 = 1000479002;

pub const TIME_DOMAIN_PRESENT_STAGE_LOCAL_EXT: i32 = 1000208000;
pub const TIME_DOMAIN_SWAPCHAIN_LOCAL_EXT: i32 = 1000208001;
pub const ERROR_PRESENT_TIMING_QUEUE_FULL_EXT: i32 = -1000208000;
pub const SWAPCHAIN_CREATE_PRESENT_TIMING_BIT_EXT: u32 = 1 << 9;
pub const SWAPCHAIN_CREATE_PRESENT_ID_2_BIT_KHR: u32 = 1 << 6;
pub const PRESENT_STAGE_QUEUE_OPERATIONS_END_BIT_EXT: u32 = 1 << 0;
pub const PRESENT_STAGE_REQUEST_DEQUEUED_BIT_EXT: u32 = 1 << 1;
pub const PRESENT_STAGE_IMAGE_FIRST_PIXEL_OUT_BIT_EXT: u32 = 1 << 2;
pub const PRESENT_STAGE_IMAGE_FIRST_PIXEL_VISIBLE_BIT_EXT: u32 = 1 << 3;
/// Short names of the four stages, indexed by bit position.
pub const STAGES: [&str; 4] = ["QUEUE_OPERATIONS_END", "REQUEST_DEQUEUED", "IMAGE_FIRST_PIXEL_OUT", "IMAGE_FIRST_PIXEL_VISIBLE"];

#[repr(C)]
#[derive(Clone, Copy)]
pub struct PhysicalDevicePresentTimingFeaturesEXT {
    pub s_type: vk::StructureType,
    pub p_next: *mut c_void,
    pub present_timing: vk::Bool32,
    pub present_at_absolute_time: vk::Bool32,
    pub present_at_relative_time: vk::Bool32,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct PresentTimingSurfaceCapabilitiesEXT {
    pub s_type: vk::StructureType,
    pub p_next: *mut c_void,
    pub present_timing_supported: vk::Bool32,
    pub present_at_absolute_time_supported: vk::Bool32,
    pub present_at_relative_time_supported: vk::Bool32,
    pub present_stage_queries: u32,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct SwapchainCalibratedTimestampInfoEXT {
    pub s_type: vk::StructureType,
    pub p_next: *const c_void,
    pub swapchain: vk::SwapchainKHR,
    pub present_stage: u32,
    pub time_domain_id: u64,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct SwapchainTimingPropertiesEXT {
    pub s_type: vk::StructureType,
    pub p_next: *mut c_void,
    pub refresh_duration: u64,
    pub refresh_interval: u64,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct SwapchainTimeDomainPropertiesEXT {
    pub s_type: vk::StructureType,
    pub p_next: *mut c_void,
    pub time_domain_count: u32,
    pub p_time_domains: *mut vk::TimeDomainKHR,
    pub p_time_domain_ids: *mut u64,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct PastPresentationTimingInfoEXT {
    pub s_type: vk::StructureType,
    pub p_next: *const c_void,
    pub flags: u32,
    pub swapchain: vk::SwapchainKHR,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct PastPresentationTimingPropertiesEXT {
    pub s_type: vk::StructureType,
    pub p_next: *mut c_void,
    pub timing_properties_counter: u64,
    pub time_domains_counter: u64,
    pub presentation_timing_count: u32,
    pub p_presentation_timings: *mut PastPresentationTimingEXT,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct PastPresentationTimingEXT {
    pub s_type: vk::StructureType,
    pub p_next: *mut c_void,
    pub present_id: u64,
    pub target_time: u64,
    pub present_stage_count: u32,
    pub p_present_stages: *mut PresentStageTimeEXT,
    pub time_domain: vk::TimeDomainKHR,
    pub time_domain_id: u64,
    pub report_complete: vk::Bool32,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct PresentTimingsInfoEXT {
    pub s_type: vk::StructureType,
    pub p_next: *const c_void,
    pub swapchain_count: u32,
    pub p_timing_infos: *const PresentTimingInfoEXT,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct PresentTimingInfoEXT {
    pub s_type: vk::StructureType,
    pub p_next: *const c_void,
    pub flags: u32,
    pub target_time: u64,
    pub time_domain_id: u64,
    pub present_stage_queries: u32,
    pub target_time_domain_present_stage: u32,
}

#[repr(C)]
#[derive(Clone, Copy, Default)]
pub struct PresentStageTimeEXT {
    pub stage: u32,
    pub time: u64,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct PhysicalDevicePresentId2FeaturesKHR {
    pub s_type: vk::StructureType,
    pub p_next: *mut c_void,
    pub present_id2: vk::Bool32,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct SurfaceCapabilitiesPresentId2KHR {
    pub s_type: vk::StructureType,
    pub p_next: *mut c_void,
    pub present_id2_supported: vk::Bool32,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct PresentId2KHR {
    pub s_type: vk::StructureType,
    pub p_next: *const c_void,
    pub swapchain_count: u32,
    pub p_present_ids: *const u64,
}

/// A zeroed Vulkan input/output struct with its sType set. Every struct above that has an
/// sType has it at offset 0 as an i32 (asserted in layout_check.rs).
pub fn new<T: Copy>(s_type: i32) -> T {
    unsafe {
        let mut v: T = std::mem::zeroed();
        *(&mut v as *mut T as *mut i32) = s_type;
        v
    }
}

pub type PfnSetSwapchainPresentTimingQueueSizeEXT = unsafe extern "system" fn(vk::Device, vk::SwapchainKHR, u32) -> vk::Result;
pub type PfnGetSwapchainTimingPropertiesEXT =
    unsafe extern "system" fn(vk::Device, vk::SwapchainKHR, *mut SwapchainTimingPropertiesEXT, *mut u64) -> vk::Result;
pub type PfnGetSwapchainTimeDomainPropertiesEXT =
    unsafe extern "system" fn(vk::Device, vk::SwapchainKHR, *mut SwapchainTimeDomainPropertiesEXT, *mut u64) -> vk::Result;
pub type PfnGetPastPresentationTimingEXT =
    unsafe extern "system" fn(vk::Device, *const PastPresentationTimingInfoEXT, *mut PastPresentationTimingPropertiesEXT) -> vk::Result;

pub const COMMAND_NAMES: [&CStr; 4] = [
    c"vkSetSwapchainPresentTimingQueueSizeEXT",
    c"vkGetSwapchainTimingPropertiesEXT",
    c"vkGetSwapchainTimeDomainPropertiesEXT",
    c"vkGetPastPresentationTimingEXT",
];

/// The four VK_EXT_present_timing device commands.
pub struct PresentTiming {
    pub set_queue_size: PfnSetSwapchainPresentTimingQueueSizeEXT,
    pub timing_properties: PfnGetSwapchainTimingPropertiesEXT,
    pub time_domains: PfnGetSwapchainTimeDomainPropertiesEXT,
    pub past: PfnGetPastPresentationTimingEXT,
}

impl PresentTiming {
    /// None if the device returns no address for any of them.
    pub unsafe fn load(instance: &ash::Instance, device: vk::Device) -> Option<Self> {
        let get = |name: &CStr| unsafe { instance.get_device_proc_addr(device, name.as_ptr()) };
        Some(Self {
            set_queue_size: std::mem::transmute(get(COMMAND_NAMES[0])?),
            timing_properties: std::mem::transmute(get(COMMAND_NAMES[1])?),
            time_domains: std::mem::transmute(get(COMMAND_NAMES[2])?),
            past: std::mem::transmute(get(COMMAND_NAMES[3])?),
        })
    }
}
