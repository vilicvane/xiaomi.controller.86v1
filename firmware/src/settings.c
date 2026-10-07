#include "panel.h"
#include "http.h"

#define OPEN FN(int (*)(const char *, int, unsigned), 0x3802c901u)
#define READ FN(int (*)(void *, void *, unsigned), 0x3802954du)
#define WRITE FN(int (*)(int, const void *, unsigned), 0x3802b379u)
#define SYNC FN(int (*)(int), 0x3802b3edu)
#define SETTINGS_MAGIC 0x31545256u

struct saved { u32 magic, sequence, seconds, check; };

PREFIX static void *fat_file(int fd)
{
    void *file = 0;
    if (GETFILE(fd, &file) < 0 || !file) return 0;
    u32 inode = WORD((u32)file + 0x10u);
    if (!inode || (BYTE(inode + 0xeu) & 15u) != 3u || WORD(inode + 0x10u) != 0x383f18dcu)
        return 0;
    return file;
}

static const char *path(unsigned slot)
{
    return slot ? "/data/86v1-return.1" : "/data/86v1-return.0";
}

/* 0=absent, 1=valid, 2=damaged project record, -1=I/O, -2=foreign file. */
__attribute__((section(".text.broker.settings")))
static int read_slot(unsigned slot, struct saved *value)
{
    int fd = OPEN(path(slot), 1, 0);
    if (fd < 0) return *ERRNO() == 2 ? 0 : -1;
    void *file = fat_file(fd);
    u32 data[5];
    int bytes = file ? READ(file, data, 17) : -1;
    int close = CLOSE(fd);
    if (bytes < 0 || close) return -1;
    if (bytes < 4 || data[0] != SETTINGS_MAGIC) return -2;
    if (bytes != 16 || data[2] > 3600u || (data[1] & 1u) != slot ||
        data[3] != (data[0] ^ data[1] ^ data[2])) return 2;
    *value = (struct saved){data[0], data[1], data[2], data[3]};
    return 1;
}

void panel_settings_load(struct panel_settings_store *store)
{
    struct saved a, b;
    int first = read_slot(0, &a), second = read_slot(1, &b);
    store->sequence = 0; store->seconds = 60;
    if (first == 1 || second == 1) {
        struct saved *newest = second == 1 && (first != 1 || (int)(b.sequence - a.sequence) > 0) ? &b : &a;
        store->sequence = newest->sequence; store->seconds = newest->seconds;
    }
}

unsigned panel_settings_save(struct panel_settings_store *store, unsigned seconds)
{
    struct saved previous;
    unsigned slot = (store->sequence + 1u) & 1u;
    int exists = read_slot(slot, &previous);
    if (exists < 0) return exists == -2 ? 409 : 503;
    exists = read_slot(slot ^ 1u, &previous);
    if (exists < 0) return exists == -2 ? 409 : 503;
    struct saved next = {SETTINGS_MAGIC, store->sequence + 1u, seconds, 0};
    next.check = next.magic ^ next.sequence ^ next.seconds;
    int fd = OPEN(path(slot), 0x26, 0644);
    if (fd < 0) return 503;
    int okay = fat_file(fd) && WRITE(fd, &next, sizeof(next)) == (int)sizeof(next) && !SYNC(fd);
    if (CLOSE(fd)) okay = 0;
    if (!okay || read_slot(slot, &previous) != 1 || previous.sequence != next.sequence || previous.seconds != seconds)
        return 503;
    store->sequence = next.sequence; store->seconds = seconds;
    return 0;
}
