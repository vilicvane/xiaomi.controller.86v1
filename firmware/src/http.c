#include "panel.h"
#include "http.h"

int panel_exact(int fd, u8 *data, u32 bytes, u32 start, u32 sending)
{
    u32 last;
    if (panel_clock(&last)) return -1;
    while (bytes) {
        u32 now;
        if (panel_clock(&now) || now - start >= 30000u || now - last >= 5000u) return -1;
        int n = sending ? SEND(fd, data, bytes, 0x40) : RECEIVE(fd, data, bytes, 0x40, 0, 0);
        if (n > 0 && (u32)n <= bytes) { data += n; bytes -= (u32)n; last = now; }
        else if (n < 0 && (*ERRNO() == 11 || *ERRNO() == 4)) SLEEP(&pause20, 0);
        else return -1;
    }
    return 0;
}

struct incoming {
    int fd;
    u8 *cached;
    u32 bytes, start;
};

static int body(struct incoming *input, u8 *destination, u32 bytes)
{
    u32 count = input->bytes < bytes ? input->bytes : bytes;
    for (u32 i = 0; i < count; ++i) destination[i] = input->cached[i];
    input->cached += count;
    input->bytes -= count;
    return panel_exact(input->fd, destination + count, bytes - count, input->start, 0);
}

static unsigned headers(struct incoming *input, u8 *buffer,
                        struct panel_http_request *request)
{
    u32 used = 0, last = input->start;
    while (used < PANEL_HTTP_HEADER_BYTES) {
        u32 now;
        if (panel_clock(&now) || now - input->start >= 30000u || now - last >= 5000u) return 408;
        int n = RECEIVE(input->fd, buffer + used, PANEL_HTTP_HEADER_BYTES - used, 0x40, 0, 0);
        if (n > 0 && (u32)n <= PANEL_HTTP_HEADER_BYTES - used) {
            used += (u32)n;
            last = now;
            unsigned end = panel_http_header_end((char *)buffer, used);
            if (end) {
                input->cached = buffer + end;
                input->bytes = used - end;
                return panel_http_parse((char *)buffer, end, request);
            }
        } else if (n < 0 && (*ERRNO() == 11 || *ERRNO() == 4)) SLEEP(&pause20, 0);
        else return 400;
    }
    return 431;
}

static unsigned image(struct broker *c, struct incoming *input)
{
    u32 header[4];
    if (body(input, (u8 *)header, sizeof(header)) || header[0] != 0x474d4956u ||
        header[1] != 0x014001e0u || header[2] != PANEL_IMAGE_BYTES) return 400;
    u8 *destination = 0;
    if (!LOCK(c->mutex, 0)) { destination = (u8 *)c->receive; UNLOCK(c->mutex); }
    if (!destination) return 503;
    if (body(input, destination, PANEL_IMAGE_BYTES)) return 400;
    u32 checksum = 2166136261u;
    for (u32 i = 0; i < PANEL_IMAGE_BYTES; ++i) checksum = (checksum ^ destination[i]) * 16777619u;
    if (checksum != header[3]) return 422;
    unsigned status = 503;
    if (!LOCK(c->mutex, 0)) {
        if (c->alive) { c->image_pending = 1; status = 202; }
        UNLOCK(c->mutex);
    }
    return status;
}

static void reply(struct broker *c, int fd, char *buffer, unsigned status)
{
    static const char welcome[] =
        "Panel image drawer\nFrontend URL is not configured.\n"
        "POST /api/image accepts VIMG + 480x320 RGB565LE.\n";
    unsigned size = status == 200 ? sizeof(welcome) - 1u : 0;
    /* HTTP/1.1 permits an empty reason phrase after the status code and space. */
    int n = SNPRINTF(buffer, PANEL_HTTP_HEADER_BYTES,
        "HTTP/1.1 %u \r\nConnection: close\r\nContent-Length: %u\r\n"
        "Content-Type: text/plain; charset=utf-8\r\nCache-Control: no-store\r\n"
        "Access-Control-Allow-Origin: %s\r\n"
        "Access-Control-Allow-Methods: POST\r\nAccess-Control-Allow-Headers: Content-Type\r\n"
        "Allow: GET, POST, OPTIONS\r\n", status, size, PANEL_FRONTEND_ORIGIN);
    if (n < 0 || (u32)n >= PANEL_HTTP_HEADER_BYTES) return;
    u32 used = (u32)n;
    if (status == 303) {
        const u8 *ip = (const u8 *)&c->ipv4;
        char separator = '?';
        for (const char *p = PANEL_FRONTEND_URL; *p; ++p)
            if (*p == '?') separator = '&';
        n = SNPRINTF(buffer + used, PANEL_HTTP_HEADER_BYTES - used,
            "Location: %s%cdevice=http%%3A%%2F%%2F%u.%u.%u.%u%%3A%u\r\n",
            PANEL_FRONTEND_URL, separator, ip[0], ip[1], ip[2], ip[3], PANEL_PORT);
        if (n < 0 || (u32)n >= PANEL_HTTP_HEADER_BYTES - used) return;
        used += (u32)n;
    }
    if (used + 2u > PANEL_HTTP_HEADER_BYTES) return;
    buffer[used++] = '\r'; buffer[used++] = '\n';
    u32 start;
    if (panel_clock(&start) || panel_exact(fd, (u8 *)buffer, used, start, 1)) return;
    if (size) panel_exact(fd, (u8 *)welcome, size, start, 1);
}

void panel_server(struct broker *c)
{
    u8 *buffer = ALLOC(PANEL_HTTP_HEADER_BYTES);
    if (!buffer) { c->server_error = 4; return; }
    struct { u16 family, port; u32 address; u8 zero[8]; } addr = {2, 0xa646, 0, {0}};
    int listener = SOCKET(2, 0x801, 0);
    if (listener < 0) { c->server_error = 1; FREE(buffer); return; }
    if (BIND(listener, &addr, 16) || LISTEN(listener, 1)) {
        c->server_error = 2; CLOSE(listener); FREE(buffer); return;
    }
    c->server_state = 1;
    u32 address_ms = 0;
    int address_started = 0;
    while (c->alive) {
        if (c->image_pending) { SLEEP(&pause20, 0); continue; }
        u32 address_now;
        if (!panel_clock(&address_now) &&
            (!address_started || address_now - address_ms >= 1000u)) {
            address_ms = address_now; address_started = 1;
            u32 address = 0, query[10]; ZERO(query, 0, sizeof(query));
            query[0] = 0x6e616c77u; query[1] = 0x30u;
            if (!IOCTL(listener, 0x701, query) && (query[5] & 0xffffu) == 2u) address = query[6];
            if (!LOCK(c->mutex, 0)) {
                if (c->ipv4 != address) { c->ipv4 = address; c->dirty = 1; }
                UNLOCK(c->mutex);
            }
        }
        int fd = ACCEPT(listener, 0, 0);
        if (fd < 0) {
            int error = *ERRNO();
            if (error != 11 && error != 4) c->server_error = 3;
            SLEEP(&pause20, 0); continue;
        }
        c->server_state = 2;
        struct incoming input = {fd, buffer, 0, 0};
        struct panel_http_request request;
        unsigned status = panel_clock(&input.start) ? 503 : headers(&input, buffer, &request);
        if (!status) {
            if (request.method == PANEL_HTTP_POST) status = image(c, &input);
            else if (request.method == PANEL_HTTP_OPTIONS) status = 204;
            else status = PANEL_FRONTEND_URL[0] ? 303 : 200;
        }
        reply(c, fd, (char *)buffer, status);
        CLOSE(fd);
        c->server_error = status < 400 ? 0 : status;
        c->server_state = 1;
    }
    CLOSE(listener); FREE(buffer); c->server_state = 0;
}
