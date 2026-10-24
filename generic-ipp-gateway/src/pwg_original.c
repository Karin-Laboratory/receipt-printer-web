#define _GNU_SOURCE
#include "gateway.h"
#include <cups/raster.h>
#include <fcntl.h>
#include <limits.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/*
 * Read the ORIGINAL PWG document, not PAPPL's regenerated fixed-height
 * output. All rows, including intentional white margins, are retained.
 * Unlike PAPPL's output callbacks this sees the sender's cupsHeight.
 */
bool
gw_pwg_render_original(pappl_job_t *job)
{
  const char *path = papplJobGetFilename(job);
  cups_raster_t *raster = NULL;
  cups_page_header2_t h;
  unsigned char *row = NULL;
  int fd = -1;
  unsigned pages = 0;
  bool ok = false;
  if (!path || !*path) return false;
  fd = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
  if (fd < 0) return false;
  raster = cupsRasterOpen(fd, CUPS_RASTER_READ);
  if (!raster) goto done;
  while (cupsRasterReadHeader2(raster, &h)) {
    if (++pages > 200 || h.cupsHeight == 0 || h.cupsHeight > 65535u ||
        h.cupsWidth < GW_WIDTH_DOTS || h.cupsWidth > 600 ||
        h.cupsBitsPerPixel != 1 || h.cupsBitsPerColor != 1 ||
        h.cupsColorOrder != CUPS_ORDER_CHUNKED ||
        (h.cupsColorSpace != CUPS_CSPACE_K && h.cupsColorSpace != CUPS_CSPACE_W) ||
        h.cupsBytesPerLine < (h.cupsWidth + 7u) / 8u ||
        h.cupsBytesPerLine > 1024) goto done;
    row = malloc(h.cupsBytesPerLine);
    if (!row) goto done;
    if (!gw_escpos_page_begin(GW_WIDTH_DOTS, h.cupsHeight)) goto done;
    for (unsigned y = 0; y < h.cupsHeight; y++) {
      if (cupsRasterReadPixels(raster, row, h.cupsBytesPerLine) != h.cupsBytesPerLine)
        goto done;
      if (h.cupsColorSpace == CUPS_CSPACE_W) {
        for (unsigned j = 0; j < h.cupsBytesPerLine; j++) row[j] = (unsigned char)~row[j];
      }
      if (!gw_escpos_row(row, h.cupsWidth, y)) goto done;
    }
    if (!gw_escpos_page_end()) goto done;
    free(row); row = NULL;
  }
  ok = pages > 0 && !gw_capture.failed;
done:
  free(row);
  if (raster) cupsRasterClose(raster);
  close(fd);
  return ok;
}
