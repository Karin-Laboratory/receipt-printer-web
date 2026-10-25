/* Offline-only PWG Raster to exact-page-size PDF bridge.
 * Decodes original PWG raster pages BEFORE PAPPL can add fixed media padding.
 * The resulting PDF is re-rasterized by the existing capture-only PDF filter.
 */
#include <cups/raster.h>
#include <zlib.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>

#define MAX_PAGES 200u
#define MAX_JOB (64u * 1024u * 1024u)
static long offsets[3 * MAX_PAGES + 3];
static int mark(FILE *fp, unsigned id) {
  long p = ftell(fp);
  if (p < 0 || id >= sizeof(offsets) / sizeof(offsets[0])) return 0;
  offsets[id] = p;
  return 1;
}
static int put_object(FILE *fp, unsigned id, const char *body) {
  return mark(fp,id) && fprintf(fp,"%u 0 obj\n%s\nendobj\n",id,body) > 0;
}
int main(int argc, char **argv) {
  FILE *out = NULL;
  int fd = -1, error = 1;
  cups_raster_t *r = NULL;
  cups_page_header2_t h;
  unsigned pages = 0, total_id, total_unpacked = 0;
  if (argc != 3 || !strcmp(argv[1],argv[2])) return 2;
  fd = open(argv[1], 0);
  if (fd < 0) goto done;
  r = cupsRasterOpen(fd,CUPS_RASTER_READ);
  if (!r) goto done;
  out = fopen(argv[2],"wb");
  if (!out) goto done;
  if (fprintf(out,"%%PDF-1.4\n%%ReceiptGateway\n") < 0) goto done;
  while (cupsRasterReadHeader2(r,&h)) {
    unsigned id = 3 + 3 * pages;
    size_t rawlen, packedlen;
    unsigned char *raw = NULL, *packed = NULL;
    unsigned long n;
    char body[400], content[200];
    int ok = 0;
    if (pages >= MAX_PAGES || h.cupsWidth != 512u ||
        h.cupsHeight == 0 || h.cupsHeight > 65535u ||
        h.cupsBitsPerPixel != 1 || h.cupsBitsPerColor != 1 ||
        h.cupsColorOrder != CUPS_ORDER_CHUNKED ||
        (h.cupsColorSpace != CUPS_CSPACE_K && h.cupsColorSpace != CUPS_CSPACE_W) ||
        h.cupsBytesPerLine != 64u) goto done;
    rawlen = 64u * (size_t)h.cupsHeight;
    if (rawlen > MAX_JOB - total_unpacked) goto done;
    raw = malloc(rawlen);
    if (!raw) goto page_done;
    for (unsigned y=0;y<h.cupsHeight;y++) {
      if (cupsRasterReadPixels(r,raw+64u*y,64u)!=64u) goto page_done;
    }
    total_unpacked += (unsigned)rawlen;
    if (h.cupsColorSpace == CUPS_CSPACE_K)
      for (size_t i=0;i<rawlen;i++) raw[i] = (unsigned char)~raw[i];
    packedlen = (size_t)compressBound((uLong)rawlen);
    packed = malloc(packedlen);
    if (!packed) goto page_done;
    n = (uLong)packedlen;
    if (compress2(packed,&n,raw,(uLong)rawlen,Z_BEST_SPEED)!=Z_OK) goto page_done;
    snprintf(body,sizeof(body),
      "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 204.8 %.4f] /Resources << /XObject << /Im0 %u 0 R >> >> /Contents %u 0 R >>",
      (double)h.cupsHeight * .4, id+1,id+2);
    if (!put_object(out,id,body) || !mark(out,id+1)) goto page_done;
    if (fprintf(out,"%u 0 obj\n<< /Type /XObject /Subtype /Image /Width 512 /Height %u /ColorSpace /DeviceGray /BitsPerComponent 1 /Filter /FlateDecode /Length %lu >>\nstream\n",
        id+1,h.cupsHeight,n)<0) goto page_done;
    if (fwrite(packed,1,(size_t)n,out)!=(size_t)n || fprintf(out,"\nendstream\nendobj\n")<0) goto page_done;
    int cn=snprintf(content,sizeof(content),"q 204.8 0 0 %.4f 0 0 cm /Im0 Do Q\n",(double)h.cupsHeight*.4);
    if (cn<0 || (size_t)cn>=sizeof(content) || !mark(out,id+2)) goto page_done;
    if (fprintf(out,"%u 0 obj\n<< /Length %d >>\nstream\n",id+2,cn)<0 ||
        fwrite(content,1,(size_t)cn,out)!=(size_t)cn ||
        fprintf(out,"endstream\nendobj\n")<0) goto page_done;
    ok=1;
page_done:
    free(raw);free(packed);
    if (!ok) goto done;
    pages++;
  }
  if (!pages) goto done;
  total_id = 2 + 3*pages;
  if (!put_object(out,1,"<< /Type /Catalog /Pages 2 0 R >>") || !mark(out,2)) goto done;
  if (fprintf(out,"2 0 obj\n<< /Type /Pages /Count %u /Kids [",pages)<0) goto done;
  for (unsigned i=0;i<pages;i++) if (fprintf(out,"%u 0 R ",3+3*i)<0) goto done;
  if (fprintf(out,"] >>\nendobj\n")<0) goto done;
  long xref=ftell(out);
  if (xref<0 || fprintf(out,"xref\n0 %u\n0000000000 65535 f \n",total_id+1)<0) goto done;
  for (unsigned i=1;i<=total_id;i++)
    if (offsets[i]<=0 || fprintf(out,"%010ld 00000 n \n",offsets[i])<0) goto done;
  if (fprintf(out,"trailer\n<< /Size %u /Root 1 0 R >>\nstartxref\n%ld\n%%%%EOF\n",total_id+1,xref)<0) goto done;
  if (fflush(out) || ferror(out)) goto done;
  error=0;
done:
  if (r) cupsRasterClose(r);
  if (fd>=0) close(fd);
  if (out && fclose(out)) error=1;
  if (error && argc==3) unlink(argv[2]);
  return error;
}
