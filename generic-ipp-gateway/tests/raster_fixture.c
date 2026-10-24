#include <cups/raster.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv)
{
  FILE *fp;
  cups_raster_t *r;
  cups_page_header2_t h;
  unsigned char row[64];
  char *end;
  long pages, rows = 3;
  if (argc != 3 && argc != 4) return 2;
  pages = strtol(argv[2], &end, 10);
  if (*end || pages < 1 || pages > 20) return 2;
  if (argc == 4) { rows = strtol(argv[3], &end, 10); if (*end || rows < 1 || rows > 1200) return 2; }
  if (!(fp = fopen(argv[1], "wb"))) return 1;
  r = cupsRasterOpen(fileno(fp), CUPS_RASTER_WRITE_PWG);
  if (!r) { fclose(fp); return 1; }
  for (long p = 0; p < pages; p++) {
    memset(&h, 0, sizeof(h));
    h.cupsWidth = 512; h.cupsHeight = (unsigned)rows;
    h.HWResolution[0] = h.HWResolution[1] = 180;
    h.cupsBitsPerColor = h.cupsBitsPerPixel = 1;
    h.cupsBytesPerLine = 64;
    h.cupsColorOrder = CUPS_ORDER_CHUNKED;
    h.cupsColorSpace = CUPS_CSPACE_K;
    h.cupsNumColors = 1;
    h.cupsPageSize[0] = 8000.0f; h.cupsPageSize[1] = (float)rows * 25.4f / 180.0f;
    h.cupsImagingBBox[2] = 8000.0f; h.cupsImagingBBox[3] = h.cupsPageSize[1];
    if (!cupsRasterWriteHeader2(r, &h)) { cupsRasterClose(r); fclose(fp); return 1; }
    for (unsigned y = 0; y < h.cupsHeight; y++) {
      memset(row, 0, sizeof(row));
      if (y == 0) {
        unsigned marker_x = 27u + (unsigned)p;
        row[marker_x / 8] |= (unsigned char)(0x80u >> (marker_x % 8));
      }
      if (y == 1) { row[10] = 0x1d; row[11] = 0x56; row[12] = 0x00; }
      if (cupsRasterWritePixels(r, row, sizeof(row)) != sizeof(row)) { cupsRasterClose(r); fclose(fp); return 1; }
    }
  }
  cupsRasterClose(r);
  return fclose(fp) ? 1 : 0;
}
