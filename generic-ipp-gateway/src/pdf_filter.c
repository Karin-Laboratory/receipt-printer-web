#define _GNU_SOURCE
#include "gateway.h"
#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <dirent.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/wait.h>

static bool
read_token(FILE *fp, char *buf, size_t size)
{
  int c;
  size_t n = 0;
  do {
    c = fgetc(fp);
    if (c == '#') { while (c != '\n' && c != EOF) c = fgetc(fp); }
  } while (c != EOF && isspace((unsigned char)c));
  if (c == EOF) return false;
  do {
    if (n + 1 >= size) return false;
    buf[n++] = (char)c;
    c = fgetc(fp);
  } while (c != EOF && !isspace((unsigned char)c) && c != '#');
  buf[n] = '\0';
  return c != EOF;
}

static bool
pgm_info(FILE *fp, unsigned *width, unsigned *height)
{
  char t[32]; char *end;
  if (!read_token(fp, t, sizeof(t)) || strcmp(t, "P5")) return false;
  if (!read_token(fp, t, sizeof(t))) return false;
  unsigned long w = strtoul(t, &end, 10); if (*end || w != GW_WIDTH_DOTS) return false;
  if (!read_token(fp, t, sizeof(t))) return false;
  unsigned long h = strtoul(t, &end, 10); if (*end || h == 0 || h > GW_MAX_PAGE_HEIGHT) return false;
  if (!read_token(fp, t, sizeof(t)) || strcmp(t, "255")) return false;
  *width = (unsigned)w; *height = (unsigned)h;
  return true;
}

static bool
render_pdf(const char *input, const char *prefix)
{
  pid_t pid = fork();
  if (pid < 0) return false;
  if (pid == 0) {
    struct rlimit cpu = { 30, 30 }, files = { 256, 256 }, fsize = { 64 * 1024 * 1024, 64 * 1024 * 1024 }, as = { 768 * 1024 * 1024, 768 * 1024 * 1024 };
    setrlimit(RLIMIT_CPU, &cpu); setrlimit(RLIMIT_NOFILE, &files);
    setrlimit(RLIMIT_FSIZE, &fsize); setrlimit(RLIMIT_AS, &as);
    execl("/usr/bin/pdftoppm", "pdftoppm", "-f", "1", "-l", "201", "-scale-to-x", "512",
           "-scale-to-y", "-1", "-gray", "-forcenum", input, prefix, (char *)NULL);
    _exit(127);
  }
  int status;
  while (waitpid(pid, &status, 0) < 0) if (errno != EINTR) return false;
  return WIFEXITED(status) && WEXITSTATUS(status) == 0;
}

static void
remove_rendered(const char *dir, unsigned pages)
{
  DIR *dp = opendir(dir);
  struct dirent *de;
  if (dp) {
    while ((de = readdir(dp)) != NULL)
      if (!strncmp(de->d_name, "page-", 5)) unlinkat(dirfd(dp), de->d_name, 0);
    closedir(dp);
  }
  (void)pages;
  rmdir(dir);
}

static void
page_path(char *path, size_t pathsize, const char *dir, unsigned page, unsigned digits)
{
  snprintf(path, pathsize, "%s/page-%0*u.pgm", dir, (int)digits, page);
}

bool
gw_pdf_filter(pappl_job_t *job, pappl_device_t *device, void *data)
{
  const char *input = papplJobGetFilename(job);
  char tmp[] = "/tmp/receipt-pdf-XXXXXX";
  char prefix[512], path[512];
  struct stat st;
  unsigned pages = 0;
  unsigned digits = 1;
  pappl_printer_t *printer = papplJobGetPrinter(job);
  pappl_pr_driver_data_t driver;
  pappl_pr_options_t local_options;
  pappl_pr_options_t *options = &local_options;
  bool started = false, ok = false;
  (void)data;
  if (!input || stat(input, &st) < 0 || !S_ISREG(st.st_mode) || st.st_size <= 0 ||
      (uint64_t)st.st_size > GW_MAX_JOB_BYTES) goto done;
  if (!mkdtemp(tmp)) goto done;
  snprintf(prefix, sizeof(prefix), "%s/page", tmp);
  if (!render_pdf(input, prefix)) goto cleanup;
  for (digits = 1; digits <= 3; digits++) {
    page_path(path, sizeof(path), tmp, 1, digits);
    if (access(path, R_OK) == 0) break;
  }
  if (digits > 3) goto cleanup;
  for (unsigned i = 1; i <= 201; i++) {
    page_path(path, sizeof(path), tmp, i, digits);
    if (access(path, R_OK) < 0) break;
    pages++;
  }
  if (!pages || pages > 200) goto cleanup;
  if (!papplPrinterGetDriverData(printer, &driver)) goto cleanup;
  memset(&local_options, 0, sizeof(local_options));
  local_options.num_pages = pages;
  local_options.copies = 1;
  local_options.media = driver.media_default;
  local_options.printer_resolution[0] = local_options.printer_resolution[1] = 180;
  local_options.sides = PAPPL_SIDES_ONE_SIDED;
  local_options.print_color_mode = PAPPL_COLOR_MODE_BI_LEVEL;
  local_options.print_scaling = PAPPL_SCALING_AUTO_FIT;
  if (!driver.rstartjob_cb(job, options, device)) goto cleanup;
  started = true;
  for (unsigned page = 1; page <= pages; page++) {
    FILE *fp;
    unsigned width, height;
    unsigned char gray[GW_WIDTH_DOTS], packed[GW_WIDTH_DOTS / 8];
    page_path(path, sizeof(path), tmp, page, digits);
    fp = fopen(path, "rb");
    if (!fp || !pgm_info(fp, &width, &height)) { if (fp) fclose(fp); papplLogJob(job, PAPPL_LOGLEVEL_ERROR, "Invalid rendered PGM page %u", page); goto abort_job; }
    memset(&options->header, 0, sizeof(options->header));
    options->header.cupsWidth = width;
    options->header.cupsHeight = height;
    options->header.cupsBitsPerColor = 1;
    options->header.cupsBitsPerPixel = 1;
    options->header.cupsBytesPerLine = width / 8;
    options->header.cupsColorOrder = CUPS_ORDER_CHUNKED;
    options->header.cupsColorSpace = CUPS_CSPACE_K;
    options->header.HWResolution[0] = options->header.HWResolution[1] = 180;
    options->header.cupsPageSize[0] = 8000.0f;
    options->header.cupsPageSize[1] = (float)height * 25.4f / 180.0f;
    if (!driver.rstartpage_cb(job, options, device, page - 1)) { fclose(fp); papplLogJob(job, PAPPL_LOGLEVEL_ERROR, "Could not start raster page %u", page); goto abort_job; }
    for (unsigned y = 0; y < height; y++) {
      if (fread(gray, 1, width, fp) != width) { fclose(fp); papplLogJob(job, PAPPL_LOGLEVEL_ERROR, "Short read on rendered page %u row %u", page, y); goto abort_job; }
      memset(packed, 0, sizeof(packed));
      for (unsigned x = 0; x < width; x++) if (gray[x] < 128) packed[x / 8] |= (unsigned char)(0x80u >> (x & 7));
      if (!driver.rwriteline_cb(job, options, device, y, packed)) { fclose(fp); papplLogJob(job, PAPPL_LOGLEVEL_ERROR, "Could not write raster page %u row %u", page, y); goto abort_job; }
    }
    if (fgetc(fp) != EOF) { fclose(fp); papplLogJob(job, PAPPL_LOGLEVEL_ERROR, "Rendered page %u has trailing data", page); goto abort_job; }
    fclose(fp);
    if (!driver.rendpage_cb(job, options, device, page - 1)) { papplLogJob(job, PAPPL_LOGLEVEL_ERROR, "Could not finish raster page %u", page); goto abort_job; }
  }
  ok = driver.rendjob_cb(job, options, device);
  started = false;
  goto cleanup;

abort_job:
  if (started) { gw_abort_current_job(job); started = false; }
done:
  papplJobSetReasons(job, PAPPL_JREASON_DOCUMENT_FORMAT_ERROR | PAPPL_JREASON_ERRORS_DETECTED, 0);
cleanup:
  if (strcmp(tmp, "/tmp/receipt-pdf-XXXXXX")) remove_rendered(tmp, pages);
  return ok;
}
