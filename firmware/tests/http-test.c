#include "http.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static unsigned checks;

static void check(const char *data, unsigned bytes, unsigned expected,
                  unsigned method, unsigned length)
{
    struct panel_http_request request = {0xabcdefu, 0x123456u};
    unsigned status = panel_http_parse(data, bytes, &request);
    if (status != expected) {
        fprintf(stderr, "Expected HTTP %u, received %u: %.*s\n", expected, status, (int)bytes, data);
        assert(status == expected);
    }
    if (!status) assert(request.method == method && request.length == length);
    else assert(request.method == 0xabcdefu && request.length == 0x123456u);
    ++checks;
}

#define CHECK(text, status, method, length) check(text, sizeof(text) - 1, status, method, length)
#define POST "POST /api/image HTTP/1.1\r\nHost: panel\r\nContent-Type: application/octet-stream\r\n"

int main(void)
{
    CHECK("GET / HTTP/1.1\r\nHost: panel:18086\r\n\r\n", 0, PANEL_HTTP_GET, 0);
    CHECK("GET / HTTP/1.0\r\n\r\n", 0, PANEL_HTTP_GET, 0);
    CHECK("OPTIONS /api/image HTTP/1.1\r\nHost: panel\r\nOrigin: https://example.com\r\n"
          "Access-Control-Request-Method: POST\r\nAccess-Control-Request-Headers: content-type\r\n\r\n",
          0, PANEL_HTTP_OPTIONS, 0);
    CHECK(POST "Content-Length: 307216\r\n\r\n", 0, PANEL_HTTP_POST, PANEL_HTTP_BODY_BYTES);
    CHECK("POST /api/image HTTP/1.1\r\nhOsT: panel\r\ncOnTeNt-TyPe: APPLICATION/OCTET-STREAM\r\n"
          "cOnTeNt-LeNgTh:\t000307216 \t\r\n\r\n", 0, PANEL_HTTP_POST, PANEL_HTTP_BODY_BYTES);
    CHECK("GET / HTTP/1.1\r\nHost: panel\r\nContent-Length: 0\r\n\r\n", 0, PANEL_HTTP_GET, 0);
    CHECK("GET / HTTP/1.1\r\n\r\n", 400, 0, 0);
    CHECK("GET / HTTP/1.1\r\nHost:\r\n\r\n", 400, 0, 0);
    CHECK("GET / HTTP/1.1\r\nHost: panel\r\nHOST: panel\r\n\r\n", 400, 0, 0);
    CHECK("PUT /api/image HTTP/1.1\r\nHost: panel\r\n\r\n", 405, 0, 0);
    CHECK("get / HTTP/1.1\r\nHost: panel\r\n\r\n", 405, 0, 0);
    CHECK("GET /api/image HTTP/1.1\r\nHost: panel\r\n\r\n", 404, 0, 0);
    CHECK("POST / HTTP/1.1\r\nHost: panel\r\n\r\n", 404, 0, 0);
    CHECK("GET /?device=panel HTTP/1.1\r\nHost: panel\r\n\r\n", 404, 0, 0);
    CHECK("GET / HTTP/2.0\r\nHost: panel\r\n\r\n", 400, 0, 0);
    CHECK("GET  / HTTP/1.1\r\nHost: panel\r\n\r\n", 400, 0, 0);
    CHECK("GET / HTTP/1.1 \r\nHost: panel\r\n\r\n", 400, 0, 0);
    CHECK("GET / HTTP/1.1\nHost: panel\n\n", 400, 0, 0);
    CHECK("GET / HTTP/1.1\r\nHost: panel\r\n folded\r\n\r\n", 400, 0, 0);
    CHECK("GET / HTTP/1.1\r\nHost : panel\r\n\r\n", 400, 0, 0);
    CHECK("GET / HTTP/1.1\r\n: value\r\nHost: panel\r\n\r\n", 400, 0, 0);
    CHECK("GET / HTTP/1.1\r\nHost: panel\r\nX: a\0b\r\n\r\n", 400, 0, 0);
    CHECK("GET / HTTP/1.1\r\nHost: panel\r\nX: a\nb\r\n\r\n", 400, 0, 0);
    CHECK("GET / HTTP/1.1\r\nHost: panel\r\nX: a\177b\r\n\r\n", 400, 0, 0);
    CHECK(POST "\r\n", 411, 0, 0);
    CHECK(POST "Content-Length: 307215\r\n\r\n", 400, 0, 0);
    CHECK(POST "Content-Length: 307217\r\n\r\n", 413, 0, 0);
    CHECK(POST "Content-Length: 4294967295\r\n\r\n", 413, 0, 0);
    CHECK(POST "Content-Length: 4294967296\r\n\r\n", 400, 0, 0);
    CHECK(POST "Content-Length: 999999999999999999999\r\n\r\n", 400, 0, 0);
    CHECK(POST "Content-Length:\r\n\r\n", 400, 0, 0);
    CHECK(POST "Content-Length: +307216\r\n\r\n", 400, 0, 0);
    CHECK(POST "Content-Length: -307216\r\n\r\n", 400, 0, 0);
    CHECK(POST "Content-Length: 307216x\r\n\r\n", 400, 0, 0);
    CHECK(POST "Content-Length: 307216,307216\r\n\r\n", 400, 0, 0);
    CHECK(POST "Content-Length: 307216\r\nContent-Length: 307216\r\n\r\n", 400, 0, 0);
    CHECK(POST "Content-Length: 307216\r\nTransfer-Encoding: chunked\r\n\r\n", 400, 0, 0);
    CHECK(POST "Transfer-Encoding: identity\r\n\r\n", 400, 0, 0);
    CHECK(POST "Content-Length: 307216\r\nExpect: 100-continue\r\n\r\n", 417, 0, 0);
    CHECK("POST /api/image HTTP/1.1\r\nHost: panel\r\nContent-Length: 307216\r\n\r\n", 415, 0, 0);
    CHECK("POST /api/image HTTP/1.1\r\nHost: panel\r\nContent-Length: 307216\r\n"
          "Content-Type: text/plain\r\n\r\n", 415, 0, 0);
    CHECK(POST "Content-Length: 307216\r\nContent-Type: application/octet-stream\r\n\r\n", 400, 0, 0);
    CHECK("OPTIONS /api/image HTTP/1.1\r\nHost: panel\r\nContent-Length: 1\r\n\r\n", 400, 0, 0);
    CHECK("GET / HTTP/1.1\r\nHost: panel\r\nContent-Length: 1\r\n\r\n", 400, 0, 0);

    const char complete[] = POST "Content-Length: 307216\r\n\r\n";
    for (unsigned i = 0; i < sizeof(complete) - 1; ++i) {
        assert(!panel_http_header_end(complete, i));
        check(complete, i, 400, 0, 0);
    }
    assert(panel_http_header_end(complete, sizeof(complete) - 1) == sizeof(complete) - 1);
    const char with_body[] = "GET / HTTP/1.1\r\nHost: panel\r\n\r\n\0\1\2\3";
    unsigned end = panel_http_header_end(with_body, sizeof(with_body) - 1);
    check(with_body, end, 0, PANEL_HTTP_GET, 0);
    check(with_body, sizeof(with_body) - 1, 400, 0, 0);

    char limit[PANEL_HTTP_HEADER_BYTES + 1];
    const char prefix[] = "GET / HTTP/1.1\r\nHost: panel\r\nX: ";
    memcpy(limit, prefix, sizeof(prefix) - 1);
    memset(limit + sizeof(prefix) - 1, 'x', sizeof(limit) - sizeof(prefix) + 1);
    memcpy(limit + PANEL_HTTP_HEADER_BYTES - 4, "\r\n\r\n", 4);
    check(limit, PANEL_HTTP_HEADER_BYTES, 0, PANEL_HTTP_GET, 0);
    check(limit, PANEL_HTTP_HEADER_BYTES + 1, 431, 0, 0);
    for (unsigned i = 0; i < sizeof(complete) - 1; ++i) {
        char modified[sizeof(complete)];
        memcpy(modified, complete, sizeof(complete));
        modified[i] = '\0';
        check(modified, sizeof(complete) - 1, 400, 0, 0);
    }
    printf("HTTP parser: %u checks passed\n", checks);
    return 0;
}
