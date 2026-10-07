#include "http.h"

static int equal(const char *data, unsigned bytes, const char *text, int fold)
{
    unsigned i;
    for (i = 0; i < bytes; ++i) {
        unsigned char v = (unsigned char)data[i];
        if (!text[i]) return 0;
        if (fold && v >= 'A' && v <= 'Z') v += 'a' - 'A';
        if (v != (unsigned char)text[i]) return 0;
    }
    return !text[i];
}

static int token(unsigned char v)
{
    if ((v >= 'a' && v <= 'z') || (v >= 'A' && v <= 'Z') ||
        (v >= '0' && v <= '9')) return 1;
    const char *symbols = "!#$%&'*+-.^_`|~";
    while (*symbols) if (v == (unsigned char)*symbols++) return 1;
    return 0;
}

unsigned panel_http_header_end(const char *data, unsigned bytes)
{
    for (unsigned i = 3; i < bytes; ++i)
        if (data[i - 3] == '\r' && data[i - 2] == '\n' &&
            data[i - 1] == '\r' && data[i] == '\n') return i + 1;
    return 0;
}

unsigned panel_http_parse(const char *data, unsigned bytes,
                          struct panel_http_request *request)
{
    if (bytes > PANEL_HTTP_HEADER_BYTES) return 431;
    if (!bytes || panel_http_header_end(data, bytes) != bytes) return 400;
    unsigned end = 0;
    while (end + 1 < bytes && data[end] != '\r') ++end;
    if (end + 1 >= bytes || data[end + 1] != '\n') return 400;
    for (unsigned i = 0; i < end; ++i)
        if ((unsigned char)data[i] < 32 || (unsigned char)data[i] >= 127) return 400;
    unsigned first = 0, second;
    while (first < end && data[first] != ' ') ++first;
    second = first + 1;
    while (second < end && data[second] != ' ') ++second;
    if (!first || second <= first + 1 || second >= end) return 400;
    unsigned version = second + 1;
    int http11 = equal(data + version, end - version, "HTTP/1.1", 0);
    if (!http11 && !equal(data + version, end - version, "HTTP/1.0", 0)) return 400;
    unsigned method = equal(data, first, "GET", 0) ? PANEL_HTTP_GET :
                      equal(data, first, "POST", 0) ? PANEL_HTTP_POST :
                      equal(data, first, "OPTIONS", 0) ? PANEL_HTTP_OPTIONS : 0;
    unsigned target = first + 1, target_bytes = second - target;
    unsigned pos = end + 2, length = 0, has_length = 0, has_host = 0, has_type = 0;
    while (pos < bytes - 2) {
        end = pos;
        while (end + 1 < bytes && data[end] != '\r') ++end;
        if (end + 1 >= bytes || data[end + 1] != '\n') return 400;
        unsigned colon = pos;
        while (colon < end && token((unsigned char)data[colon])) ++colon;
        if (colon == pos || colon == end || data[colon] != ':') return 400;
        unsigned value = colon + 1, value_end = end;
        for (unsigned i = value; i < end; ++i)
            if (((unsigned char)data[i] < 32 && data[i] != '\t') || data[i] == 127) return 400;
        while (value < value_end && (data[value] == ' ' || data[value] == '\t')) ++value;
        while (value_end > value && (data[value_end - 1] == ' ' || data[value_end - 1] == '\t')) --value_end;
        if (equal(data + pos, colon - pos, "transfer-encoding", 1)) return 400;
        if (equal(data + pos, colon - pos, "expect", 1)) return 417;
        if (equal(data + pos, colon - pos, "content-length", 1)) {
            if (has_length++ || value == value_end) return 400;
            for (unsigned i = value; i < value_end; ++i) {
                unsigned digit = (unsigned char)data[i] - '0';
                if (digit > 9 || length > (0xffffffffu - digit) / 10u) return 400;
                length = length * 10u + digit;
            }
        }
        if (equal(data + pos, colon - pos, "host", 1))
            if (has_host++ || value == value_end) return 400;
        if (equal(data + pos, colon - pos, "content-type", 1)) {
            if (has_type++) return 400;
            if (!equal(data + value, value_end - value, "application/octet-stream", 1)) has_type = 2;
        }
        pos = end + 2;
    }
    if (http11 && !has_host) return 400;
    if (!method) return 405;
    if (!equal(data + target, target_bytes,
               method == PANEL_HTTP_GET ? "/" : "/api/image", 0)) return 404;
    if (method == PANEL_HTTP_POST) {
        if (!has_length) return 411;
        if (length != PANEL_HTTP_BODY_BYTES) return length > PANEL_HTTP_BODY_BYTES ? 413 : 400;
        if (has_type != 1) return 415;
    } else if (length) return 400;
    request->method = method;
    request->length = length;
    return 0;
}
