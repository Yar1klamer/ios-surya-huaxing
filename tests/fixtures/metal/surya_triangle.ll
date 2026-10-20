; Authored synthetic AIR-shaped render pipeline. No Apple binary input.
target triple = "air64-apple-ios16.0.0"
define <4 x float> @surya_vertex(i32 %vid) {
  %first = icmp eq i32 %vid, 0
  %second = icmp eq i32 %vid, 1
  %third = icmp eq i32 %vid, 2
  %right = select i1 %second, float 7.500000e-01, float 0.000000e+00
  %x = select i1 %first, float -7.500000e-01, float %right
  %y = select i1 %third, float 7.500000e-01, float -7.500000e-01
  %xy = insertelement <4 x float> <float 0.0, float 0.0, float 0.0, float 1.0>, float %x, i32 0
  %position = insertelement <4 x float> %xy, float %y, i32 1
  ret <4 x float> %position
}
define <4 x float> @surya_fragment() {
  ret <4 x float> <float 1.0, float 0.0, float 0.0, float 1.0>
}
!air.vertex = !{!0}
!air.fragment = !{!4}
!air.version = !{!8}
!air.language_version = !{!9}
!0 = !{ptr @surya_vertex, !1, !2}
!1 = !{!3}
!2 = !{!7}
!3 = !{!"air.position", !"air.arg_type_name", !"float4"}
!4 = !{ptr @surya_fragment, !5, !6}
!5 = !{!10}
!6 = !{}
!7 = !{i32 0, !"air.vertex_id", !"air.arg_type_name", !"uint", !"air.arg_name", !"vid"}
!8 = !{i32 2, i32 4, i32 0}
!9 = !{!"Metal", i32 3, i32 0, i32 0}
!10 = !{!"air.render_target", i32 0, i32 0, !"air.arg_type_name", !"float4"}
