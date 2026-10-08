#ifndef MI_PANEL_HTTP_H
#define MI_PANEL_HTTP_H

#define PANEL_HTTP_HEADER_BYTES 2048u
#define PANEL_HTTP_BODY_BYTES 307216u
#define PANEL_HTTP_IMAGE_MAX_BYTES 1048576u
#define PANEL_SETTINGS_BODY_BYTES 64u

enum panel_http_method {
    PANEL_HTTP_GET = 1,
    PANEL_HTTP_POST,
    PANEL_HTTP_OPTIONS
};

enum panel_http_resource { PANEL_HTTP_ROOT, PANEL_HTTP_IMAGE, PANEL_HTTP_SETTINGS };

struct panel_http_request {
    unsigned method, length, resource;
};

/* Zero means incomplete; otherwise the result includes the final CRLF. */
unsigned panel_http_header_end(const char *data, unsigned bytes);
/* Returns 0 on success or the HTTP rejection status. */
unsigned panel_http_parse(const char *data, unsigned bytes,
                          struct panel_http_request *request);
unsigned panel_settings_parse(const char *data, unsigned bytes, unsigned *seconds);

struct panel_settings_store { unsigned sequence, seconds; };
void panel_settings_load(struct panel_settings_store *store);
unsigned panel_settings_save(struct panel_settings_store *store, unsigned seconds);

#endif
