#ifndef RECEIPT_GATEWAY_H
#define RECEIPT_GATEWAY_H

#include <pappl/pappl.h>
#include <pthread.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define GW_WIDTH_DOTS 512
#define GW_MAX_JOB_BYTES (64u * 1024u * 1024u)
#define GW_MAX_PAGE_HEIGHT 65535

typedef struct {
  int fd;
  int dirfd;
  char partial[96];
  char final[96];
  int job_id;
  size_t bytes;
  unsigned pages;
  unsigned cuts;
  bool failed;
  bool active;
} gw_capture_t;

extern char gw_capture_dir[4096];
extern pthread_mutex_t gw_job_mutex;
extern gw_capture_t gw_capture;

bool gw_capture_init(const char *path);
bool gw_capture_begin(int job_id);
bool gw_capture_write(const void *data, size_t len);
bool gw_capture_finish(bool success);
void gw_register_capture_device(void);
bool gw_escpos_page_begin(unsigned width, unsigned height);
bool gw_escpos_row(const unsigned char *line, unsigned width, unsigned row);
bool gw_escpos_page_end(void);
bool gw_escpos_cut(void);
bool gw_driver(pappl_system_t *, const char *, const char *, const char *, pappl_pr_driver_data_t *, ipp_t **, void *);
bool gw_pwg_render_original(pappl_job_t *job);
bool gw_pdf_filter(pappl_job_t *, pappl_device_t *, void *);
void gw_abort_current_job(pappl_job_t *job);

#endif
