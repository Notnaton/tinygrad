__kernel void matmul_f32(__global const float *a, __global const float *b, __global float *out, int width) {
  const size_t row = get_global_id(1), col = get_global_id(0);
  if (row >= (size_t)width || col >= (size_t)width) return;
  float acc = 0.0f;
  for (int k = 0; k < width; k++) acc += a[row * width + k] * b[k * width + col];
  out[row * width + col] = acc;
}
