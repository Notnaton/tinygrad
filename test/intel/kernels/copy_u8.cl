__kernel void copy_u8(__global const uchar *src, __global uchar *dst, int count) {
  const size_t gid = get_global_id(0);
  if (gid < (size_t)count) dst[gid] = src[gid];
}
