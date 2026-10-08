#include "image-store.h"
#include "image-codec.h"

#define STORE __attribute__((section(".text.image.store")))
#define STORE_DATA __attribute__((section(".rodata.image.store")))
#define OPEN FN(int (*)(const char *, int, unsigned), 0x3802c901u)
#define READ FN(int (*)(void *, void *, unsigned), 0x3802954du)
#define WRITE FN(int (*)(int, const void *, unsigned), 0x3802b379u)
#define SYNC FN(int (*)(int), 0x3802b3edu)
#define COPY FN(void *(*)(void *, const void *, u32), 0x383d8ac0u)
#define IMAGE_MAGIC 0x31495056u /* VPI1, little endian. */
#define IMAGE_LIMIT 1048576u
#define HASH_START 0x811c9dc5u
#define CHUNK 512u

/* Twenty bytes on disk, followed by the complete original encoded file.
 * Header check is FNV-1a over its first sixteen bytes. Sequence parity owns
 * the slot; signed subtraction orders successive records across u32 wrap.
 */
struct image_record { u32 magic, sequence, length, hash, check; };
_Static_assert(sizeof(struct image_record) == 20, "Image record layout changed");

static const char path0[] STORE_DATA = "/data/86v1-image.0";
static const char path1[] STORE_DATA = "/data/86v1-image.1";

STORE static const char *path(unsigned slot) { return slot ? path1 : path0; }

STORE static u32 hash(u32 state, const u8 *data, u32 bytes)
{
    while (bytes--) state = (state ^ *data++) * 0x01000193u;
    return state;
}

STORE static void *fat_file(int fd)
{
    void *file = 0;
    if (GETFILE(fd, &file) < 0 || !file) return 0;
    u32 inode = WORD((u32)file + 0x10u);
    if (!inode || (BYTE(inode + 0xeu) & 15u) != 3u || WORD(inode + 0x10u) != 0x383f18dcu)
        return 0;
    return file;
}

/* Return a complete count, a short count on EOF, or -1 on I/O. */
STORE static int read_exact(void *file, u8 *data, u32 bytes)
{
    u32 done = 0;
    while (done < bytes) {
        int count = READ(file, data + done, bytes - done);
        if (count < 0 || (u32)count > bytes - done) return -1;
        if (!count) break;
        done += (u32)count;
    }
    return (int)done;
}

STORE static int equal(const u8 *first, const u8 *second, u32 bytes)
{
    while (bytes--) if (*first++ != *second++) return 0;
    return 1;
}

/* 0 absent; 1 complete record; 2 damaged owned record; -1 I/O/resources;
 * -2 foreign. A complete VPI1 magic proves ownership even if the remainder
 * is torn. Fewer than four bytes cannot prove ownership and stay foreign.
 * buffer is optional; compare selects readback verification rather than copy.
 */
STORE static int read_slot(unsigned slot, struct image_record *record,
                          u8 *buffer, u32 capacity, int compare)
{
    int fd = OPEN(path(slot), 1, 0);
    if (fd < 0) return *ERRNO() == 2 ? 0 : -1;
    void *file = fat_file(fd);
    struct image_record value;
    ZERO(&value, 0, sizeof value);
    u8 scratch[CHUNK];
    int status = -1;
    if (!file) goto close;
    int count = read_exact(file, (u8 *)&value, sizeof value);
    if (count < 0) goto close;
    if (count < 4 || value.magic != IMAGE_MAGIC) { status = -2; goto close; }
    status = 2;
    if (count != sizeof value || !value.length || value.length > IMAGE_LIMIT ||
        (value.sequence & 1u) != slot ||
        value.check != hash(HASH_START, (const u8 *)&value, 16) ||
        (buffer && (value.length > capacity || (compare && value.length != capacity))))
        goto close;
    u32 done = 0, checksum = HASH_START;
    while (done < value.length) {
        u32 need = value.length - done;
        if (need > CHUNK) need = CHUNK;
        count = read_exact(file, scratch, need);
        if (count < 0) { status = -1; goto close; }
        if (count != (int)need) goto close;
        checksum = hash(checksum, scratch, need);
        if (buffer) {
            if (compare) {
                if (!equal(buffer + done, scratch, need)) goto close;
            } else COPY(buffer + done, scratch, need);
        }
        done += need;
    }
    count = READ(file, scratch, 1);
    if (count < 0) { status = -1; goto close; }
    if (count || checksum != value.hash) goto close;
    *record = value;
    status = 1;
close:
    if (CLOSE(fd)) status = -1;
    return status;
}

STORE static unsigned latest(const struct image_record records[2], const int states[2])
{
    return states[1] == 1 && (states[0] != 1 || (int)(records[1].sequence - records[0].sequence) > 0);
}

STORE static int write_exact(int fd, const u8 *data, u32 bytes)
{
    u32 done = 0;
    while (done < bytes) {
        u32 need = bytes - done;
        if (need > CHUNK) need = CHUNK;
        int count = WRITE(fd, data + done, need);
        if (count <= 0 || (u32)count > need) return 0;
        done += (u32)count;
    }
    return 1;
}

STORE int panel_image_save(struct panel_image_store *store, const u8 *encoded, u32 bytes)
{
    if (!bytes || bytes > IMAGE_LIMIT) return 503;
    struct image_record records[2];
    int states[2];
    states[0] = read_slot(0, records, 0, 0, 0);
    states[1] = read_slot(1, records + 1, 0, 0, 0);
    if (states[0] == -1 || states[1] == -1) return 503;
    if (states[0] == -2 || states[1] == -2) return 409;
    u32 sequence = states[0] == 1 || states[1] == 1 ? records[latest(records, states)].sequence + 1u : 1u;
    unsigned slot = sequence & 1u;
    if (store->valid) {
        unsigned known = store->sequence & 1u;
        if (states[known] != 1 || records[known].sequence != store->sequence ||
            records[known].length != store->length || records[known].hash != store->hash)
            return 503;
        slot = known ^ 1u;
        if ((sequence & 1u) != slot) ++sequence;
    }
    struct image_record next = {IMAGE_MAGIC, sequence, bytes, hash(HASH_START, encoded, bytes), 0};
    next.check = hash(HASH_START, (const u8 *)&next, 16);
    int fd = OPEN(path(slot), 0x26, 0644);
    if (fd < 0) return 503;
    int okay = fat_file(fd) && write_exact(fd, (const u8 *)&next, sizeof next) &&
               write_exact(fd, encoded, bytes) && !SYNC(fd);
    if (CLOSE(fd)) okay = 0;
    struct image_record confirmed;
    if (!okay || read_slot(slot, &confirmed, (u8 *)encoded, bytes, 1) != 1 ||
        !equal((const u8 *)&next, (const u8 *)&confirmed, sizeof next))
        return 503;
    store->sequence = sequence; store->length = bytes; store->hash = next.hash; store->valid = 1;
    return 0;
}

STORE int panel_image_load(u16 *destination, struct panel_image_store *store)
{
    ZERO(store, 0, sizeof *store);
    struct image_record records[2];
    int states[2];
    states[0] = read_slot(0, records, 0, 0, 0);
    states[1] = read_slot(1, records + 1, 0, 0, 0);
    unsigned first = latest(records, states);
    int error = 404;
    for (unsigned attempt = 0; attempt < 2; attempt++) {
        unsigned slot = first ^ attempt;
        int state = states[slot];
        if (state == 1) {
            u32 bytes = records[slot].length;
            u8 *encoded = ALLOC(bytes);
            if (!encoded) { state = -1; }
            else {
                struct image_record current;
                state = read_slot(slot, &current, encoded, bytes, 0);
                if (state == 1 && !equal((const u8 *)&current, (const u8 *)(records + slot), sizeof current)) state = 2;
                if (state == 1) {
                    int status = panel_image_decode(encoded, bytes, destination);
                    state = status ? status == 503 ? -1 : 2 : 1;
                }
                FREE(encoded);
                if (state == 1) {
                    store->sequence = current.sequence; store->length = current.length;
                    store->hash = current.hash; store->valid = 1;
                    return 0;
                }
            }
        }
        int status = state == -1 ? 503 : state == -2 ? 409 : state == 2 ? 422 : 404;
        if (status == 503 || (error != 503 && (status == 409 || (error != 409 && status == 422)))) error = status;
    }
    return error;
}
