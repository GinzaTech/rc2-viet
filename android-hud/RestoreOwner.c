#define _XOPEN_SOURCE 700

#include <ftw.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#define APP_UID_MIN 10000u
#define APP_UID_MAX 19999u
#define CACHE_GID_OFFSET 10000u

static uid_t old_uid;
static uid_t new_uid;
static struct stat walk_root;

static int fail(const char *message)
{
    fputs(message, stderr);
    return EXIT_FAILURE;
}

static int parse_uid(const char *text, uid_t *uid)
{
    unsigned int value = 0;

    if (*text == '\0')
        return 0;
    for (; *text != '\0'; ++text) {
        unsigned int digit;

        if (*text < '0' || *text > '9')
            return 0;
        digit = (unsigned int)(*text - '0');
        if (value > (APP_UID_MAX - digit) / 10u)
            return 0;
        value = value * 10u + digit;
    }
    if (value < APP_UID_MIN)
        return 0;
    *uid = (uid_t)value;
    return 1;
}

static int same_entry(const struct stat *a, const struct stat *b)
{
    return a->st_dev == b->st_dev && a->st_ino == b->st_ino &&
           (a->st_mode & S_IFMT) == (b->st_mode & S_IFMT);
}

/* Restoration requires a quiescent tree: lchown protects the final link. */
static int remap_entry(const char *path, const struct stat *walk_stat,
                       int type, struct FTW *position)
{
    struct stat before;
    struct stat after;
    uid_t uid;
    gid_t gid;

    if (type != FTW_F && type != FTW_D && type != FTW_SL)
        return 1; /* Includes FTW_NS and FTW_DNR, even below either root. */
    if (lstat(path, &before) != 0 || !same_entry(walk_stat, &before))
        return 1;
    if (position->level == 0 &&
        (!S_ISDIR(before.st_mode) || !same_entry(&walk_root, &before)))
        return 1;

    uid = before.st_uid == old_uid ? new_uid : before.st_uid;
    gid = before.st_gid;
    if (gid == (gid_t)old_uid)
        gid = (gid_t)new_uid;
    else if (gid == (gid_t)old_uid + CACHE_GID_OFFSET)
        gid = (gid_t)new_uid + CACHE_GID_OFFSET;

    if (uid == before.st_uid && gid == before.st_gid)
        return 0;
    if (lchown(path, uid == before.st_uid ? (uid_t)-1 : uid,
               gid == before.st_gid ? (gid_t)-1 : gid) != 0)
        return 1;
    if (lstat(path, &after) != 0 || !same_entry(&before, &after) ||
        after.st_uid != uid || after.st_gid != gid)
        return 1;
    return 0;
}

int main(int argc, char **argv)
{
    static const char *const roots[] = {
        "/data/user/0/dji.go.v5",
        "/data/user_de/0/dji.go.v5",
        "/data/media/0/Android/data/dji.go.v5"
    };
    struct stat root_stats[sizeof(roots) / sizeof(roots[0])];
    size_t i;

    if (argc != 3 || !parse_uid(argv[1], &old_uid) ||
        !parse_uid(argv[2], &new_uid))
        return fail("restore-owner: expected two decimal UIDs in 10000..19999\n");
    if (getuid() != 0 || geteuid() != 0)
        return fail("restore-owner: root required\n");

    /* Validate every fixed root before making any changes; reject root symlinks. */
    for (i = 0; i < sizeof(roots) / sizeof(roots[0]); ++i) {
        if (lstat(roots[i], &root_stats[i]) != 0 ||
            !S_ISDIR(root_stats[i].st_mode))
            return fail("restore-owner: invalid restoration root\n");
    }
    for (i = 0; i < sizeof(roots) / sizeof(roots[0]); ++i) {
        walk_root = root_stats[i];
        if (nftw(roots[i], remap_entry, 16, FTW_PHYS) != 0)
            return fail("restore-owner: ownership walk or verification failed\n");
    }
    return EXIT_SUCCESS;
}
