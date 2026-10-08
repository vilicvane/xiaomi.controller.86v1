#include "panel.h"
#include "http.h"
#include "image-codec.h"

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

__attribute__((section(".text.codec.http"), noinline))
static unsigned image(struct broker *c, struct incoming *input, unsigned length)
{
    u32 header[4] = {0};
    unsigned prefix = length < sizeof(header) ? length : sizeof(header);
    if (body(input, (u8 *)header, prefix)) return 400;
    int raw = header[0] == 0x474d4956u;
    if (raw) {
        if (length != PANEL_HTTP_BODY_BYTES || header[1] != 0x014001e0u ||
            header[2] != PANEL_IMAGE_BYTES) return 400;
    } else if (!((header[0] == 0x474e5089u && header[1] == 0x0a1a0a0du) ||
                 (header[0] & 0xffffu) == 0xd8ffu)) return 415;
    u8 *destination = 0;
    if (!LOCK(c->mutex, 0)) { destination = (u8 *)c->receive; UNLOCK(c->mutex); }
    if (!destination) return 503;
    if (raw) {
        if (body(input, destination, PANEL_IMAGE_BYTES)) return 400;
        u32 checksum = 2166136261u;
        for (u32 i = 0; i < PANEL_IMAGE_BYTES; ++i) checksum = (checksum ^ destination[i]) * 16777619u;
        if (checksum != header[3]) return 422;
    } else {
        u8 *encoded = ALLOC(length);
        if (!encoded) return 503;
        for (unsigned i = 0; i < prefix; ++i) encoded[i] = ((u8 *)header)[i];
        unsigned status = body(input, encoded + prefix, length - prefix) ? 400 :
                          panel_image_decode(encoded, length, (u16 *)destination);
        FREE(encoded);
        if (status) return status;
    }
    unsigned status = 503;
    if (!LOCK(c->mutex, 0)) {
        if (c->alive) { c->image_pending = 1; status = 202; }
        UNLOCK(c->mutex);
    }
    return status;
}

static void reply(struct broker *c, int fd, char *buffer, unsigned status,
                  unsigned resource, unsigned seconds)
{
    static const char welcome[] =
        "86V1 custom firmware\nFrontend URL is not configured.\n"
        "POST /api/image accepts 480x320 PNG, JPEG or VIMG.\n";
    static const char formats[] = "{\"formats\":[\"png\",\"jpeg\",\"vimg\"]}\n";
    char json[PANEL_SETTINGS_BODY_BYTES];
    unsigned size = 0;
    const char *payload = welcome;
    if (status == 200) {
        if (resource == PANEL_HTTP_SETTINGS) {
            int length = SNPRINTF(json, sizeof(json), "{\"return_after_seconds\":%u}\n", seconds);
            if (length < 0 || (unsigned)length >= sizeof(json)) return;
            size = (unsigned)length; payload = json;
        } else if (resource == PANEL_HTTP_IMAGE) {
            size = sizeof(formats) - 1u; payload = formats;
        } else size = sizeof(welcome) - 1u;
    }
    /* HTTP/1.1 permits an empty reason phrase after the status code and space. */
    int n = SNPRINTF(buffer, PANEL_HTTP_HEADER_BYTES,
        "HTTP/1.1 %u \r\nConnection: close\r\nContent-Length: %u\r\n"
        "Content-Type: %s\r\nCache-Control: no-store\r\n"
        "Access-Control-Allow-Origin: %s\r\n"
        "Access-Control-Allow-Methods: GET, POST\r\nAccess-Control-Allow-Headers: Content-Type\r\n"
        "Allow: GET, POST, OPTIONS\r\n", status, size,
        resource == PANEL_HTTP_SETTINGS || (resource == PANEL_HTTP_IMAGE && status == 200) ?
        "application/json" : "text/plain; charset=utf-8", PANEL_FRONTEND_ORIGIN);
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
    if (size) panel_exact(fd, (u8 *)payload, size, start, 1);
}

void panel_server(struct broker *c)
{
    struct panel_settings_store store;
    panel_settings_load(&store);
    if (!LOCK(c->mutex, 0)) {
        c->return_after_ms = store.seconds * 1000u; c->activity_valid = 0;
        UNLOCK(c->mutex);
    }
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
        struct panel_http_request request = {0};
        unsigned seconds = 0;
        unsigned status = panel_clock(&input.start) ? 503 : headers(&input, buffer, &request);
        if (!status) {
            if (request.method == PANEL_HTTP_OPTIONS) status = 204;
            else if (request.resource == PANEL_HTTP_SETTINGS) {
                if (request.method == PANEL_HTTP_POST) {
                    char data[PANEL_SETTINGS_BODY_BYTES];
                    status = body(&input, (u8 *)data, request.length) ? 400 :
                             panel_settings_parse(data, request.length, &seconds);
                    if (!status) status = panel_settings_save(&store, seconds);
                }
                if (!status) {
                    status = 503;
                    if (!LOCK(c->mutex, 0)) {
                        if (request.method == PANEL_HTTP_POST) {
                            c->return_after_ms = seconds * 1000u; c->activity_valid = 0;
                        }
                        seconds = c->return_after_ms / 1000u;
                        UNLOCK(c->mutex); status = 200;
                    }
                }
            } else if (request.method == PANEL_HTTP_POST) status = image(c, &input, request.length);
            else if (request.resource == PANEL_HTTP_IMAGE) status = 200;
            else status = PANEL_FRONTEND_URL[0] ? 303 : 200;
        }
        reply(c, fd, (char *)buffer, status, request.resource, seconds);
        CLOSE(fd);
        c->server_error = status < 400 ? 0 : status;
        c->server_state = 1;
    }
    CLOSE(listener); FREE(buffer); c->server_state = 0;
}
