/* The syscalls newlib needs for printf and malloc, over the simulator's MMIO
 * ports. newlib here was configured --disable-newlib-supplied-syscalls, so it
 * wants the bare names, and the POSIX prototypes must match exactly.
 *
 * Anything not needed fails rather than returning a plausible value: a
 * benchmark that silently read zeros from a stubbed read() would still print a
 * number, and the number would be wrong. */
#include <errno.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#include <stdint.h>

#define MMIO_PUTC (*(volatile unsigned char *) 0x10000000u)
#define MMIO_HALT (*(volatile unsigned int  *) 0x10000004u)
#define MMIO_ICNT (*(volatile unsigned int  *) 0x10000008u)

extern char __heap_start;
extern char _stack_top;
static char *brk_ptr;

/* Instruction count so far, so a benchmark can bracket a region of interest
 * itself instead of the host guessing where it started. */
unsigned sim_icount(void) { return MMIO_ICNT; }

ssize_t write(int fd, const void *buf, size_t len)
{
    (void) fd;
    const unsigned char *p = buf;
    for (size_t i = 0; i < len; i++) MMIO_PUTC = p[i];
    return (ssize_t) len;
}

void *sbrk(intptr_t incr)
{
    if (!brk_ptr) brk_ptr = &__heap_start;
    char *prev = brk_ptr;
    /* Keep clear of the stack. Growing into it would corrupt results quietly,
     * so fail the allocation and let the caller notice. */
    if (brk_ptr + incr > &_stack_top - 65536) {
        errno = ENOMEM;
        return (void *) -1;
    }
    brk_ptr += incr;
    return prev;
}

void _exit(int code) { MMIO_HALT = (unsigned) code; for (;;) { } }

int     close(int fd)                       { (void) fd; errno = EBADF; return -1; }
int     fstat(int fd, struct stat *st)      { (void) fd; st->st_mode = S_IFCHR; return 0; }
int     isatty(int fd)                      { (void) fd; return 1; }
off_t   lseek(int fd, off_t off, int dir)   { (void) fd; (void) off; (void) dir;
                                              errno = ESPIPE; return (off_t) -1; }
ssize_t read(int fd, void *buf, size_t len) { (void) fd; (void) buf; (void) len;
                                              errno = EIO; return -1; }
int     kill(pid_t pid, int sig)            { (void) pid; (void) sig; errno = EINVAL; return -1; }
pid_t   getpid(void)                        { return 1; }
