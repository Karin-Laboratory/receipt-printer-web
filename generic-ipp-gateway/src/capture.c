#define _GNU_SOURCE
#include "gateway.h"
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

char gw_capture_dir[4096];
pthread_mutex_t gw_job_mutex = PTHREAD_MUTEX_INITIALIZER;
gw_capture_t gw_capture = { .fd = -1, .dirfd = -1 };

static bool
write_all(int fd, const void *buf, size_t len)
{
  const unsigned char *p = buf;
  while (len) {
    ssize_t n = write(fd, p, len);
    if (n < 0 && errno == EINTR) continue;
    if (n <= 0) return false;
    p += (size_t)n;
    len -= (size_t)n;
  }
  return true;
}

bool
gw_capture_init(const char *path)
{
  struct stat st;
  if (!path || path[0] != '/' || strlen(path) >= sizeof(gw_capture_dir)) return false;
  if (mkdir(path, 0700) < 0 && errno != EEXIST) return false;
  if (lstat(path, &st) < 0 || !S_ISDIR(st.st_mode) || S_ISLNK(st.st_mode) ||
      st.st_uid != geteuid() || (st.st_mode & 0077)) return false;
  if (!realpath(path, gw_capture_dir)) return false;
  return true;
}

bool
gw_capture_begin(int job_id)
{
  if (gw_capture.active || job_id <= 0) return false;
  gw_capture.dirfd = open(gw_capture_dir, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
  if (gw_capture.dirfd < 0) return false;
  memset(gw_capture.partial, 0, sizeof(gw_capture.partial));
  memset(gw_capture.final, 0, sizeof(gw_capture.final));
  snprintf(gw_capture.partial, sizeof(gw_capture.partial), "job-%d.escpos.partial", job_id);
  snprintf(gw_capture.final, sizeof(gw_capture.final), "job-%d.escpos", job_id);
  gw_capture.fd = openat(gw_capture.dirfd, gw_capture.partial,
                         O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600);
  if (gw_capture.fd < 0) {
    close(gw_capture.dirfd); gw_capture.dirfd = -1; return false;
  }
  gw_capture.job_id = job_id;
  gw_capture.bytes = 0; gw_capture.pages = 0; gw_capture.cuts = 0;
  gw_capture.failed = false; gw_capture.active = true;
  return true;
}

bool
gw_capture_write(const void *data, size_t len)
{
#ifdef GW_TESTING
  const char *fail_at = getenv("GW_TEST_FAIL_AFTER_BYTES");
  if (fail_at && *fail_at) {
    char *end = NULL;
    unsigned long limit = strtoul(fail_at, &end, 10);
    if (end && !*end && gw_capture.bytes + len > limit) {
      size_t partial = limit > gw_capture.bytes ? (size_t)(limit - gw_capture.bytes) : 0;
      if (partial) write_all(gw_capture.fd, data, partial);
      gw_capture.bytes += partial;
      gw_capture.failed = true;
      return false;
    }
  }
#endif
  if (!gw_capture.active || gw_capture.failed || len > GW_MAX_JOB_BYTES - gw_capture.bytes) {
    gw_capture.failed = true; return false;
  }
  if (!write_all(gw_capture.fd, data, len)) { gw_capture.failed = true; return false; }
  gw_capture.bytes += len;
  return true;
}

bool
gw_capture_finish(bool success)
{
  bool ok = success && gw_capture.active && !gw_capture.failed && gw_capture.cuts == 1;
  char event[256];
  if (gw_capture.fd >= 0) {
    if (ok && fsync(gw_capture.fd) < 0) ok = false;
    if (close(gw_capture.fd) < 0) ok = false;
    gw_capture.fd = -1;
  } else ok = false;
  if (gw_capture.dirfd >= 0) {
    if (ok && renameat(gw_capture.dirfd, gw_capture.partial, gw_capture.dirfd, gw_capture.final) < 0) ok = false;
    if (ok) {
      int efd = openat(gw_capture.dirfd, "events.jsonl", O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC | O_NOFOLLOW, 0600);
      int n = snprintf(event, sizeof(event), "{\"job_id\":%d,\"event\":\"complete\",\"pages\":%u,\"cuts\":%u,\"bytes\":%zu}\n",
                       gw_capture.job_id, gw_capture.pages, gw_capture.cuts, gw_capture.bytes);
      if (efd < 0 || !write_all(efd, event, (size_t)n) || fsync(efd) < 0) ok = false;
      if (efd >= 0) close(efd);
      if (!ok) unlinkat(gw_capture.dirfd, gw_capture.final, 0);
    } else if (gw_capture.partial[0]) {
      unlinkat(gw_capture.dirfd, gw_capture.partial, 0);
    }
    fsync(gw_capture.dirfd);
    close(gw_capture.dirfd); gw_capture.dirfd = -1;
  }
  gw_capture.active = false;
  gw_capture.failed = !ok;
  return ok;
}

static bool
capture_open(pappl_device_t *device, const char *uri, const char *name)
{
  (void)device; (void)name;
  return uri && strcmp(uri, "capture://local") == 0;
}

static void
capture_close(pappl_device_t *device)
{
  (void)device;
}

static ssize_t
capture_write_device(pappl_device_t *device, const void *buffer, size_t bytes)
{
  (void)device; (void)buffer; (void)bytes;
  return -1; /* The device interface is deliberately not an output path. */
}

void
gw_register_capture_device(void)
{
  papplDeviceAddScheme("capture", PAPPL_DEVTYPE_CUSTOM_LOCAL, NULL, capture_open,
                       capture_close, NULL, capture_write_device, NULL, NULL);
}
