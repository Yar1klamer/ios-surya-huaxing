; Authored synthetic AIR-shaped compute kernel, not an Apple-compiled binary.
; Equivalent operation: dst[tid] = src[tid] for uint buffers 0 and 1.
target triple = "air64-apple-ios16.0.0"
define void @surya_copy(ptr addrspace(1) %src, ptr addrspace(1) %dst, i32 %tid) {
  %index = zext i32 %tid to i64
  %input = getelementptr i32, ptr addrspace(1) %src, i64 %index
  %value = load i32, ptr addrspace(1) %input, align 4
  %output = getelementptr i32, ptr addrspace(1) %dst, i64 %index
  store i32 %value, ptr addrspace(1) %output, align 4
  ret void
}
!air.kernel = !{!0}
!air.version = !{!6}
!air.language_version = !{!7}
!0 = !{ptr @surya_copy, !1, !2}
!1 = !{}
!2 = !{!3, !4, !5}
!3 = !{i32 0, !"air.buffer", !"air.location_index", i32 0, i32 1, !"air.read", !"air.address_space", i32 1, !"air.arg_type_size", i32 4, !"air.arg_type_align_size", i32 4, !"air.arg_type_name", !"uint", !"air.arg_name", !"src"}
!4 = !{i32 1, !"air.buffer", !"air.location_index", i32 1, i32 1, !"air.read_write", !"air.address_space", i32 1, !"air.arg_type_size", i32 4, !"air.arg_type_align_size", i32 4, !"air.arg_type_name", !"uint", !"air.arg_name", !"dst"}
!5 = !{i32 2, !"air.thread_position_in_grid", !"air.arg_type_name", !"uint", !"air.arg_name", !"tid"}
!6 = !{i32 2, i32 4, i32 0}
!7 = !{!"Metal", i32 3, i32 0, i32 0}
