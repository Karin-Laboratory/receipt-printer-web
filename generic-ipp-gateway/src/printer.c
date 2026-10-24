#define _GNU_SOURCE
#include "gateway.h"
#include <string.h>

static const char *media_names[] = { "custom_receipt_80x200mm" };

static _Thread_local bool owns_job_lock;
static _Thread_local bool native_pwg;

static bool
valid_media(pappl_job_t *job)
{
  ipp_attribute_t *attr = papplJobGetAttribute(job, "media");
  if (attr) {
    const char *name = ippGetString(attr, 0, NULL);
    if (!name || strcmp(name, "custom_receipt_80x200mm")) return false;
  }
  attr = papplJobGetAttribute(job, "media-col");
  if (attr && ippGetCount(attr) > 0) {
    ipp_t *col = ippGetCollection(attr, 0);
    ipp_attribute_t *size = col ? ippFindAttribute(col, "media-size", IPP_TAG_BEGIN_COLLECTION) : NULL;
    if (size) {
      ipp_t *dims = ippGetCollection(size, 0);
      ipp_attribute_t *width = dims ? ippFindAttribute(dims, "x-dimension", IPP_TAG_INTEGER) : NULL;
      if (width && ippGetInteger(width, 0) != 8000) return false;
    }
    ipp_attribute_t *name = col ? ippFindAttribute(col, "media-size-name", IPP_TAG_ZERO) : NULL;
    if (name) {
      const char *value = ippGetString(name, 0, NULL);
      if (!value || strcmp(value, "custom_receipt_80x200mm")) return false;
    }
  }
  return true;
}

void
gw_abort_current_job(pappl_job_t *job)
{
  if (owns_job_lock) {
    native_pwg = false;
    gw_capture_finish(false);
    owns_job_lock = false;
    pthread_mutex_unlock(&gw_job_mutex);
  }
  if (job) papplJobSetReasons(job, PAPPL_JREASON_DOCUMENT_FORMAT_ERROR | PAPPL_JREASON_ERRORS_DETECTED, 0);
}

static bool
start_job(pappl_job_t *job, pappl_pr_options_t *options, pappl_device_t *device)
{
  (void)options; (void)device;
  if (owns_job_lock) return false;
  if (!valid_media(job)) {
    papplJobSetReasons(job, PAPPL_JREASON_DOCUMENT_UNPRINTABLE_ERROR, 0);
    return false;
  }
  pthread_mutex_lock(&gw_job_mutex);
  owns_job_lock = true;
  native_pwg = false;
  if (!gw_capture_begin(papplJobGetID(job))) goto fail;
  const char *format = papplJobGetFormat(job);
  if (format && !strcmp(format, "image/pwg-raster")) {
    if (!gw_pwg_render_original(job)) goto fail_capture;
    native_pwg = true; /* Discard PAPPL's padded rendition in callbacks. */
  }
  return true;
fail_capture:
  gw_capture_finish(false);
fail:
  native_pwg = false;
  owns_job_lock = false;
  pthread_mutex_unlock(&gw_job_mutex);
  papplJobSetReasons(job, PAPPL_JREASON_ERRORS_DETECTED, 0);
  return false;
}

static bool
start_page(pappl_job_t *job, pappl_pr_options_t *options, pappl_device_t *device, unsigned page)
{
  (void)device;
  (void)job;
  (void)page;
  if (native_pwg) return owns_job_lock;
  return owns_job_lock && gw_escpos_page_begin(GW_WIDTH_DOTS,
                                               (unsigned)options->header.cupsHeight);
}

static bool
write_line(pappl_job_t *job, pappl_pr_options_t *options, pappl_device_t *device,
           unsigned y, const unsigned char *line)
{
  (void)job; (void)device;
  if (native_pwg) return owns_job_lock;
  if (!owns_job_lock || options->header.cupsBitsPerPixel != 1 || options->header.cupsWidth < GW_WIDTH_DOTS || options->header.cupsWidth > 600)
    return false;
  return gw_escpos_row(line, (unsigned)options->header.cupsWidth, y);
}

static bool
end_page(pappl_job_t *job, pappl_pr_options_t *options, pappl_device_t *device, unsigned page)
{
  (void)job; (void)options; (void)device; (void)page;
  if (native_pwg) return owns_job_lock;
  return owns_job_lock && gw_escpos_page_end();
}

static bool
end_job(pappl_job_t *job, pappl_pr_options_t *options, pappl_device_t *device)
{
  bool success = false;
  (void)options; (void)device;
  if (!owns_job_lock) return false;
  if (!gw_capture.failed && gw_capture.pages > 0 && gw_escpos_cut())
    success = gw_capture_finish(true);
  else
    gw_capture_finish(false);
  owns_job_lock = false;
  native_pwg = false;
  pthread_mutex_unlock(&gw_job_mutex);
  if (!success) papplJobSetReasons(job, PAPPL_JREASON_ERRORS_DETECTED, 0);
  return success;
}

bool
gw_driver(pappl_system_t *system, const char *driver_name, const char *device_uri,
          const char *device_id, pappl_pr_driver_data_t *data, ipp_t **attrs, void *user_data)
{
  (void)system; (void)driver_name; (void)device_id; (void)attrs; (void)user_data;
  if (!device_uri || strcmp(device_uri, "capture://local")) return false;
  memset(data, 0, sizeof(*data));
  data->make_and_model[0] = '\0';
  snprintf(data->make_and_model, sizeof(data->make_and_model), "%s", "Capture-only 80 mm Receipt Gateway");
  data->kind = PAPPL_KIND_RECEIPT | PAPPL_KIND_ROLL;
  data->ppm = 1;
  data->format = "application/vnd.receipt-capture-raster";
  data->raster_types = PAPPL_PWG_RASTER_TYPE_BLACK_1;
  data->force_raster_type = PAPPL_PWG_RASTER_TYPE_BLACK_1;
  data->color_supported = PAPPL_COLOR_MODE_BI_LEVEL;
  data->color_default = PAPPL_COLOR_MODE_BI_LEVEL;
  data->content_default = PAPPL_CONTENT_AUTO;
  data->quality_default = IPP_QUALITY_NORMAL;
  data->scaling_default = PAPPL_SCALING_AUTO_FIT;
  data->sides_supported = PAPPL_SIDES_ONE_SIDED;
  data->sides_default = PAPPL_SIDES_ONE_SIDED;
  data->duplex = PAPPL_DUPLEX_NONE;
  data->orient_default = IPP_ORIENT_PORTRAIT;
  data->finishings = PAPPL_FINISHINGS_NONE;
  data->num_resolution = 1;
  data->x_resolution[0] = data->y_resolution[0] = 180;
  data->x_default = data->y_default = 180;
  data->borderless = true;
  /* 80 mm media minus 3.89 mm margins on each side gives 512 dots at 180 dpi. */
  data->left_right = 389;
  data->bottom_top = 0;
  data->num_media = 1;
  data->media[0] = media_names[0];
  data->media_default.size_width = 8000;
  data->media_default.size_length = 20000;
  data->media_default.left_margin = data->media_default.right_margin = 389;
  data->media_default.top_margin = data->media_default.bottom_margin = 0;
  snprintf(data->media_default.size_name, sizeof(data->media_default.size_name), "%s", media_names[0]);
  data->media_default.tracking = PAPPL_MEDIA_TRACKING_CONTINUOUS;
  snprintf(data->media_default.source, sizeof(data->media_default.source), "%s", "roll-80mm");
  snprintf(data->media_default.type, sizeof(data->media_default.type), "%s", "stationery");
  data->media_ready[0] = data->media_default;
  data->num_source = 1;
  data->source[0] = "roll-80mm";
  data->num_type = 1;
  data->type[0] = "stationery";
  data->num_bin = 1;
  data->bin[0] = "face-down";
  data->bin_default = 0;
  data->tracking_supported = PAPPL_MEDIA_TRACKING_CONTINUOUS;
  data->rstartjob_cb = start_job;
  data->rstartpage_cb = start_page;
  data->rwriteline_cb = write_line;
  data->rendpage_cb = end_page;
  data->rendjob_cb = end_job;
  return true;
}
