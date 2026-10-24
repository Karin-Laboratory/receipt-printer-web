#include "gateway.h"

bool
gw_escpos_page_begin(unsigned width, unsigned height)
{
  unsigned char cmd[8];
  unsigned bytes_per_row;
  if (width != GW_WIDTH_DOTS || height == 0 || height > GW_MAX_PAGE_HEIGHT) return false;
  bytes_per_row = (width + 7) / 8;
  cmd[0] = 0x1d; cmd[1] = 0x76; cmd[2] = 0x30; cmd[3] = 0;
  cmd[4] = (unsigned char)(bytes_per_row & 0xff);
  cmd[5] = (unsigned char)((bytes_per_row >> 8) & 0xff);
  cmd[6] = (unsigned char)(height & 0xff);
  cmd[7] = (unsigned char)((height >> 8) & 0xff);
  return gw_capture_write(cmd, sizeof(cmd));
}

bool
gw_escpos_row(const unsigned char *line, unsigned width, unsigned row)
{
  unsigned char output[GW_WIDTH_DOTS / 8] = { 0 };
  int offset;
  (void)row;
  if (!line || width < GW_WIDTH_DOTS || width > 600) return false;
  offset = (int)(width - GW_WIDTH_DOTS) / 2;
  for (unsigned x = 0; x < GW_WIDTH_DOTS; x++) {
    unsigned src = x + (unsigned)offset;
    if (line[src / 8] & (unsigned char)(0x80u >> (src & 7)))
      output[x / 8] |= (unsigned char)(0x80u >> (x & 7));
  }
  return gw_capture_write(output, sizeof(output));
}

bool
gw_escpos_page_end(void)
{
  gw_capture.pages++;
  return true; /* Page transitions never emit feed or cut commands. */
}

bool
gw_escpos_cut(void)
{
  static const unsigned char full_cut[] = { 0x1d, 0x56, 0x00 };
  if (gw_capture.cuts != 0) { gw_capture.failed = true; return false; }
  if (!gw_capture_write(full_cut, sizeof(full_cut))) return false;
  gw_capture.cuts++;
  return true;
}
