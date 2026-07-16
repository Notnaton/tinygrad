__kernel void add_f32(__global const float *a, __global const float *b, __global float *out, int count) {
  const size_t gid = get_global_id(0);
  if (gid < (size_t)count) out[gid] = a[gid] + b[gid];
}
