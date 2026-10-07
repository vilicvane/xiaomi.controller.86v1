#ifndef MI_PANEL_HTTP_H
#define MI_PANEL_HTTP_H

#define PANEL_HTTP_HEADER_BYTES 2048u
#define PANEL_HTTP_BODY_BYTES 307216u

enum panel_http_method {
    PANEL_HTTP_GET = 1,
    PANEL_HTTP_POST,
    PANEL_HTTP_OPTIONS
};

struct panel_http_request {
    unsigned method, length;
};

/* Zero means incomplete; otherwise the result includes the final CRLF. */
unsigned panel_http_header_end(const char *data, unsigned bytes);
/* Returns 0 on success or the HTTP rejection status. */
unsigned panel_http_parse(const char *data, unsigned bytes,
                          struct panel_http_request *request);

#endif
