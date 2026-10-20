//! CPU Vulkan semantic smoke test. Never claims to exercise the Poco GPU.
use metal2vulkan::library::Library;
use metal2vulkan_runtime::{
    CommandBufferStatus, Device, DeviceKind, DeviceOptions, PipelineOptions, ResourceOptions, Size,
};
use std::{error::Error, path::PathBuf, time::Duration};

fn main() -> Result<(), Box<dyn Error>> {
    let mut args = std::env::args_os().skip(1);
    let air = PathBuf::from(args.next().ok_or("expected synthetic surya_copy.air")?);
    let cache = PathBuf::from(args.next().ok_or("expected scratch cache directory")?);
    if args.next().is_some() {
        return Err("unexpected arguments".into());
    }
    let mut options = DeviceOptions::default();
    options.kinds = vec![DeviceKind::Cpu];
    options.shader_cache.directory = Some(cache);
    let device = Device::system_default_with(&options)?;
    println!("HOST CPU VULKAN ONLY: {}", device.name());
    let library = device.new_library_with_compile_library(Library::from_air(&std::fs::read(air)?)?);
    let function = library.new_function_with_name("surya_copy")?;
    let state =
        device.new_compute_pipeline_state_with_function(&function, &PipelineOptions::default())?;
    let expected: Vec<u8> = (0..64u32)
        .flat_map(|i| (i.wrapping_mul(0x1234567) ^ 0xdeadbeef).to_le_bytes())
        .collect();
    let input = device.new_buffer_with_bytes(&expected, ResourceOptions::shared())?;
    let output =
        device.new_buffer_with_bytes(&vec![0x55; expected.len()], ResourceOptions::shared())?;
    let queue = device.new_command_queue()?;
    let commands = queue.command_buffer()?;
    let mut encoder = commands.compute_command_encoder()?;
    encoder.set_compute_pipeline_state(&state)?;
    encoder.set_buffer(Some(&input), 0, 0)?;
    encoder.set_buffer(Some(&output), 0, 1)?;
    encoder.dispatch_threads(Size::new(64, 1, 1), Size::new(32, 1, 1))?;
    encoder.end_encoding()?;
    commands.commit()?;
    commands
        .wait_until_completed_for(Duration::from_secs(5))
        .map_err(|_| "host Vulkan submission timed out")?;
    if commands.status() != CommandBufferStatus::Completed {
        return Err(format!("submission failed: {:?}", commands.error()).into());
    }
    let ptr = output
        .contents()
        .ok_or("shared output has no CPU mapping")?;
    // Mapping belongs to output, which remains alive; the completed submission
    // cannot write it now. Read only the allocation's known 256-byte extent.
    let actual = unsafe { std::slice::from_raw_parts(ptr.as_ptr(), expected.len()) };
    if actual != expected {
        return Err("translated kernel output differs from the 64-word reference".into());
    }
    println!("PASS: Metal-shaped runtime -> Vulkan dispatch -> exact 64-word readback");
    println!("Poco GPU execution and iOS Metal ABI remain unverified.");
    Ok(())
}
