#define _GNU_SOURCE
#include "gateway.h"
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

static void usage(const char *name)
{
  fprintf(stderr, "Usage: %s [--port PORT] [--capture-dir ABSOLUTE_PATH]\n", name);
  fprintf(stderr, "IPP listener is fixed to 127.0.0.1; printer output is capture://local only.\n");
}

int main(int argc, char **argv)
{
  int port = 8631;
  const char *capture_dir = "/tmp/receipt-ipp-capture";
  char spool_dir[4096];
  pappl_system_t *system;
  pappl_printer_t *printer;
  pappl_pr_driver_t driver = { "receipt-capture", "Capture-only 80 mm receipt gateway",
                               "MFG:Generic;MDL:Capture-only 80mm Receipt Gateway;CMD:PWG;", NULL };
  int i;

  for (i = 1; i < argc; i++) {
    if (!strcmp(argv[i], "--help")) { usage(argv[0]); return 0; }
    else if (!strcmp(argv[i], "--port") && i + 1 < argc) {
      char *end = NULL; long value = strtol(argv[++i], &end, 10);
      if (!end || *end || value < 1024 || value > 65535) { usage(argv[0]); return 2; }
      port = (int)value;
    } else if (!strcmp(argv[i], "--capture-dir") && i + 1 < argc) capture_dir = argv[++i];
    else { usage(argv[0]); return 2; }
  }
  if (!gw_capture_init(capture_dir)) {
    fprintf(stderr, "Invalid or inaccessible capture directory. Use an absolute local directory.\n");
    return 1;
  }
  if (snprintf(spool_dir, sizeof(spool_dir), "%s/spool", gw_capture_dir) >= (int)sizeof(spool_dir)) {
    fputs("Capture path is too long\n", stderr); return 1;
  }
  if (mkdir(spool_dir, 0700) < 0 && errno != EEXIST) {
    perror("create spool directory"); return 1;
  }

  gw_register_capture_device();
  system = papplSystemCreate(PAPPL_SOPTIONS_NO_TLS, "Receipt Capture Gateway", port,
                             NULL, spool_dir, "/tmp/receipt-ipp-gateway.log", PAPPL_LOGLEVEL_INFO, NULL, false);
  if (!system) { fputs("papplSystemCreate failed\n", stderr); return 1; }
  if (!papplSystemAddListeners(system, "127.0.0.1")) {
    fputs("Could not bind IPP listener to loopback\n", stderr);
    papplSystemDelete(system); return 1;
  }
  papplSystemSetMaxImageSize(system, GW_MAX_JOB_BYTES, GW_WIDTH_DOTS, GW_MAX_PAGE_HEIGHT);
  papplSystemSetPrinterDrivers(system, 1, &driver, NULL, NULL, gw_driver, NULL);
  papplSystemAddMIMEFilter(system, "application/pdf", "image/pwg-raster", gw_pdf_filter, NULL);
  printer = papplPrinterCreate(system, 1, "80mm-capture", driver.name, driver.device_id, "capture://local");
  if (!printer) {
    fputs("Could not create capture-only queue\n", stderr);
    papplSystemDelete(system); return 1;
  }
  papplSystemSetDefaultPrinterID(system, 1);
  papplPrinterSetMaxActiveJobs(printer, 16);
  fprintf(stderr, "IPP capture gateway listening only on 127.0.0.1:%d; capture directory %s\n",
          port, gw_capture_dir);
  papplSystemRun(system);
  papplSystemDelete(system);
  return 0;
}
