//! Spike S (engine spec §10.5): wl-xcon's exact drawer for one Gabor and two light-sensor
//! patches, drawn off-screen by a Vulkan compute shader on the NVIDIA GPU.
//!
//! Nothing is presented and no display is acquired: there is no swapchain, and the
//! VK_KHR_display calls below only list what the driver reports.
//!
//! Usage: spike <scene.txt> <out.f32> [runs]
//! scene.txt holds `name value` lines written by `screen.resolve` on the Mac.

#![allow(unsafe_op_in_unsafe_fn)] // the Vulkan calls are unsafe throughout; one block per fn

use ash::{khr, vk};
use std::{collections::HashMap, ffi::CStr};

/// The shader's `Params`, field for field (draw.wgsl), passed as push constants.
#[repr(C)]
#[derive(Clone, Copy)]
struct Params {
    left: [[f32; 4]; 3],
    right: [[f32; 4]; 3],
    panel_w: u32, panel_h: u32, vp_w: u32, vp_h: u32,
    pitch_x: f32, pitch_y: f32, distance: f32, ahead_x: f32,
    ahead_y: f32, background: f32, opacity: f32, radius: f32,
    sigma: f32, sf: f32, phase: f32, michelson: f32,
    cos_o: f32, sin_o: f32, patch_px: u32, patch_y: f32,
}

/// An item's direction and its own rightward and upward axes, from its position in
/// degrees (viewport.center and viewport.local_true_angle), in f64.
fn frame(x_deg: f64, y_deg: f64) -> [[f32; 4]; 3] {
    let unit = |v: [f64; 3]| { let n = v.iter().map(|a| a * a).sum::<f64>().sqrt(); v.map(|a| a / n) };
    let c = unit([x_deg.to_radians().tan(), y_deg.to_radians().tan(), 1.0]);
    let ex = unit([1.0 - c[0] * c[0], -c[0] * c[1], -c[0] * c[2]]);
    let ey = [c[1] * ex[2] - c[2] * ex[1], c[2] * ex[0] - c[0] * ex[2], c[0] * ex[1] - c[1] * ex[0]];
    [c, ex, ey].map(|v| [v[0] as f32, v[1] as f32, v[2] as f32, 0.0])
}

/// The WGSL shader, translated to SPIR-V by naga at start-up.
fn spirv() -> Vec<u32> {
    let source = include_str!("draw.wgsl");
    let module = naga::front::wgsl::parse_str(source).unwrap_or_else(|e| panic!("{}", e.emit_to_string(source)));
    let info = naga::valid::Validator::new(naga::valid::ValidationFlags::all(), naga::valid::Capabilities::IMMEDIATES)
        .validate(&module)
        .expect("the shader validates");
    let entry = naga::back::spv::PipelineOptions { shader_stage: naga::ShaderStage::Compute, entry_point: "main".into() };
    naga::back::spv::write_vec(&module, &info, &Default::default(), Some(&entry)).expect("SPIR-V")
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let text = std::fs::read_to_string(&args[1]).expect("scene file");
    let s: HashMap<&str, f64> = text
        .lines()
        .filter_map(|l| l.split_once(' '))
        .map(|(k, v)| (k, v.parse().expect("a number")))
        .collect();
    assert_eq!(s["tf"], 0.0, "a static grating: frame 0, no drift");
    let o = s["orientation"].to_radians();
    let params = Params {
        left: frame(s["left_x"], s["left_y"]),
        right: frame(s["right_x"], s["right_y"]),
        panel_w: s["panel_w"] as u32, panel_h: s["panel_h"] as u32,
        vp_w: s["vp_w"] as u32, vp_h: s["vp_h"] as u32,
        pitch_x: s["pitch_x"] as f32, pitch_y: s["pitch_y"] as f32,
        distance: s["distance"] as f32, ahead_x: s["ahead_x"] as f32, ahead_y: s["ahead_y"] as f32,
        background: s["bg_y"] as f32, opacity: s["opacity"] as f32, radius: s["radius"] as f32,
        sigma: s["sigma"] as f32, sf: s["sf"] as f32, phase: s["phase"].to_radians() as f32,
        michelson: s["michelson"] as f32, cos_o: o.cos() as f32, sin_o: o.sin() as f32,
        patch_px: 200, patch_y: s["patch_y"] as f32,
    };
    let runs = args.get(3).map_or(21, |r| r.parse().expect("a count"));
    unsafe { run(&params, &args[2], runs) }
}

/// Every display VK_KHR_display reports on `gpu`, with its modes. Read-only.
unsafe fn list_displays(entry: &ash::Entry, instance: &ash::Instance, gpu: vk::PhysicalDevice) {
    let kd = khr::display::Instance::new(entry, instance);
    let displays = kd.get_physical_device_display_properties(gpu).expect("display list");
    println!("VK_KHR_display: {} display(s)", displays.len());
    for d in displays {
        let name = if d.display_name.is_null() { "?".into() } else { CStr::from_ptr(d.display_name).to_string_lossy() };
        println!("  {name}: {}x{} px", d.physical_resolution.width, d.physical_resolution.height);
        for m in kd.get_display_mode_properties(gpu, d.display).expect("mode list") {
            let r = m.parameters.visible_region;
            println!("    mode {}x{} @ {:.3} Hz", r.width, r.height, m.parameters.refresh_rate as f64 / 1000.0);
        }
    }
}

/// The clocks the GPU's timestamps can be calibrated against (VK_KHR_calibrated_timestamps).
unsafe fn list_time_domains(entry: &ash::Entry, instance: &ash::Instance, gpu: vk::PhysicalDevice) {
    let kc = khr::calibrated_timestamps::Instance::new(entry, instance);
    println!("calibrateable time domains: {:?}", kc.get_physical_device_calibrateable_time_domains(gpu));
}

unsafe fn run(params: &Params, out_path: &str, runs: usize) {
    let entry = ash::Entry::load().expect("the Vulkan loader");
    let app = vk::ApplicationInfo::default().api_version(vk::API_VERSION_1_3);
    let extensions = [khr::surface::NAME.as_ptr(), khr::display::NAME.as_ptr()]; // to list displays only
    let instance = entry
        .create_instance(&vk::InstanceCreateInfo::default().application_info(&app).enabled_extension_names(&extensions), None)
        .expect("an instance");
    let gpu = instance
        .enumerate_physical_devices()
        .unwrap()
        .into_iter()
        .find(|&g| instance.get_physical_device_properties(g).vendor_id == 0x10de)
        .expect("an NVIDIA device");
    let props = instance.get_physical_device_properties(gpu);
    let v = props.driver_version; // NVIDIA packs it 10.8.8.6 bits
    println!("device: {:?}, driver {}.{}.{}", CStr::from_ptr(props.device_name.as_ptr()), v >> 22, (v >> 14) & 0xff, (v >> 6) & 0xff);
    list_displays(&entry, &instance, gpu);
    list_time_domains(&entry, &instance, gpu);

    let family = instance
        .get_physical_device_queue_family_properties(gpu)
        .iter()
        .position(|q| q.queue_flags.contains(vk::QueueFlags::COMPUTE) && q.timestamp_valid_bits > 0)
        .expect("a compute queue with timestamps") as u32;
    let queue_info = [vk::DeviceQueueCreateInfo::default().queue_family_index(family).queue_priorities(&[1.0])];
    let device = instance.create_device(gpu, &vk::DeviceCreateInfo::default().queue_create_infos(&queue_info), None).unwrap();
    let queue = device.get_device_queue(family, 0);

    // The output: one f32 per panel pixel, in memory the host can map.
    let size = (params.panel_w * params.panel_h * 4) as u64;
    let buffer = device
        .create_buffer(&vk::BufferCreateInfo::default().size(size).usage(vk::BufferUsageFlags::STORAGE_BUFFER), None)
        .unwrap();
    let need = device.get_buffer_memory_requirements(buffer);
    let types = instance.get_physical_device_memory_properties(gpu);
    let host = vk::MemoryPropertyFlags::HOST_VISIBLE | vk::MemoryPropertyFlags::HOST_COHERENT;
    let memory_type = [host | vk::MemoryPropertyFlags::DEVICE_LOCAL, host]
        .iter()
        .find_map(|&want| {
            (0..types.memory_type_count)
                .find(|&i| need.memory_type_bits & (1 << i) != 0 && types.memory_types[i as usize].property_flags.contains(want))
        })
        .expect("a host-visible memory type");
    println!("output memory: type {memory_type}, {:?}", types.memory_types[memory_type as usize].property_flags);
    let alloc = vk::MemoryAllocateInfo::default().allocation_size(need.size).memory_type_index(memory_type);
    let memory = device.allocate_memory(&alloc, None).unwrap();
    device.bind_buffer_memory(buffer, memory, 0).unwrap();

    // The pipeline: one storage buffer, the parameters as push constants.
    let code = spirv();
    let shader = device.create_shader_module(&vk::ShaderModuleCreateInfo::default().code(&code), None).unwrap();
    let binding = [vk::DescriptorSetLayoutBinding::default()
        .descriptor_type(vk::DescriptorType::STORAGE_BUFFER)
        .descriptor_count(1)
        .stage_flags(vk::ShaderStageFlags::COMPUTE)];
    let set_layout = device
        .create_descriptor_set_layout(&vk::DescriptorSetLayoutCreateInfo::default().bindings(&binding), None)
        .unwrap();
    let push = [vk::PushConstantRange::default().stage_flags(vk::ShaderStageFlags::COMPUTE).size(size_of::<Params>() as u32)];
    let layouts = [set_layout];
    let layout = device
        .create_pipeline_layout(&vk::PipelineLayoutCreateInfo::default().set_layouts(&layouts).push_constant_ranges(&push), None)
        .unwrap();
    let stage = vk::PipelineShaderStageCreateInfo::default().stage(vk::ShaderStageFlags::COMPUTE).module(shader).name(c"main");
    let pipeline = device
        .create_compute_pipelines(vk::PipelineCache::null(), &[vk::ComputePipelineCreateInfo::default().stage(stage).layout(layout)], None)
        .map_err(|(_, e)| e)
        .unwrap()[0];

    let pool_sizes = [vk::DescriptorPoolSize { ty: vk::DescriptorType::STORAGE_BUFFER, descriptor_count: 1 }];
    let pool = device
        .create_descriptor_pool(&vk::DescriptorPoolCreateInfo::default().max_sets(1).pool_sizes(&pool_sizes), None)
        .unwrap();
    let set = device
        .allocate_descriptor_sets(&vk::DescriptorSetAllocateInfo::default().descriptor_pool(pool).set_layouts(&layouts))
        .unwrap()[0];
    let target = [vk::DescriptorBufferInfo { buffer, offset: 0, range: vk::WHOLE_SIZE }];
    let write = vk::WriteDescriptorSet::default()
        .dst_set(set)
        .descriptor_type(vk::DescriptorType::STORAGE_BUFFER)
        .buffer_info(&target);
    device.update_descriptor_sets(&[write], &[]);

    // One command buffer: a GPU timestamp on each side of the dispatch.
    let queries = device
        .create_query_pool(&vk::QueryPoolCreateInfo::default().query_type(vk::QueryType::TIMESTAMP).query_count(2), None)
        .unwrap();
    let cmd_pool = device.create_command_pool(&vk::CommandPoolCreateInfo::default().queue_family_index(family), None).unwrap();
    let cmd = device
        .allocate_command_buffers(&vk::CommandBufferAllocateInfo::default().command_pool(cmd_pool).command_buffer_count(1))
        .unwrap()[0];
    let bytes = std::slice::from_raw_parts(params as *const Params as *const u8, size_of::<Params>());
    let compute = vk::PipelineBindPoint::COMPUTE;
    device.begin_command_buffer(cmd, &vk::CommandBufferBeginInfo::default()).unwrap();
    device.cmd_reset_query_pool(cmd, queries, 0, 2);
    device.cmd_bind_pipeline(cmd, compute, pipeline);
    device.cmd_bind_descriptor_sets(cmd, compute, layout, 0, &[set], &[]);
    device.cmd_push_constants(cmd, layout, vk::ShaderStageFlags::COMPUTE, 0, bytes);
    device.cmd_write_timestamp(cmd, vk::PipelineStageFlags::TOP_OF_PIPE, queries, 0);
    device.cmd_dispatch(cmd, params.panel_w.div_ceil(8), params.panel_h.div_ceil(8), 1);
    device.cmd_write_timestamp(cmd, vk::PipelineStageFlags::BOTTOM_OF_PIPE, queries, 1);
    let to_host = vk::MemoryBarrier::default().src_access_mask(vk::AccessFlags::SHADER_WRITE).dst_access_mask(vk::AccessFlags::HOST_READ);
    let (from, to) = (vk::PipelineStageFlags::COMPUTE_SHADER, vk::PipelineStageFlags::HOST);
    device.cmd_pipeline_barrier(cmd, from, to, vk::DependencyFlags::empty(), &[to_host], &[], &[]);
    device.end_command_buffer(cmd).unwrap();

    let fence = device.create_fence(&vk::FenceCreateInfo::default(), None).unwrap();
    let mut ms = Vec::with_capacity(runs);
    for _ in 0..runs {
        let cmds = [cmd];
        device.queue_submit(queue, &[vk::SubmitInfo::default().command_buffers(&cmds)], fence).unwrap();
        device.wait_for_fences(&[fence], true, u64::MAX).unwrap();
        device.reset_fences(&[fence]).unwrap();
        let mut ticks = [0u64; 2];
        let flags = vk::QueryResultFlags::TYPE_64 | vk::QueryResultFlags::WAIT;
        device.get_query_pool_results(queries, 0, &mut ticks, flags).unwrap();
        ms.push((ticks[1] - ticks[0]) as f64 * props.limits.timestamp_period as f64 / 1e6);
    }
    println!("dispatch, GPU timestamps, ms per run: {}", ms.iter().map(|t| format!("{t:.4}")).collect::<Vec<_>>().join(" "));
    ms.sort_by(f64::total_cmp);
    println!("dispatch: runs {runs}, median {:.4} ms, min {:.4}, max {:.4}", ms[runs / 2], ms[0], ms[runs - 1]);

    let mapped = device.map_memory(memory, 0, size, vk::MemoryMapFlags::empty()).unwrap() as *const u8;
    std::fs::write(out_path, std::slice::from_raw_parts(mapped, size as usize)).expect("write the output");
    device.unmap_memory(memory);
    println!("wrote {out_path}: {} x {} f32, row-major, top row first", params.panel_w, params.panel_h);

    device.destroy_fence(fence, None);
    device.destroy_command_pool(cmd_pool, None);
    device.destroy_query_pool(queries, None);
    device.destroy_descriptor_pool(pool, None);
    device.destroy_pipeline(pipeline, None);
    device.destroy_pipeline_layout(layout, None);
    device.destroy_descriptor_set_layout(set_layout, None);
    device.destroy_shader_module(shader, None);
    device.destroy_buffer(buffer, None);
    device.free_memory(memory, None);
    device.destroy_device(None);
    instance.destroy_instance(None);
}
