/*
 * Native Linux PAM integration module for OTP-Local resident daemon.
 *
 * Implements pam_sm_authenticate and pam_sm_setcred adhering strictly
 * to the Linux PAM SPI. Interfaces with the local resident daemon via
 * UNIX domain socket (/run/user/$UID/otp-local.sock) with fail-closed logic.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <syslog.h>
#include <errno.h>
#include <pwd.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <netinet/in.h>

#include <security/pam_appl.h>
#include <security/pam_modules.h>

#define UNIX_PATH_MAX sizeof(((struct sockaddr_un *)0)->sun_path)

struct module_options {
    int debug;
    int try_first_pass;
    int use_first_pass;
    int forward_pass;
    int echo_code;
    int nodetect;
    char account[128];
    char socket_path[UNIX_PATH_MAX];
    char prompt[128];
};

static void secure_zero(void *v, size_t n) {
    if (v == NULL) {
        return;
    }
    volatile unsigned char *p = (volatile unsigned char *)v;
    while (n--) {
        *p++ = 0;
    }
    __asm__ __volatile__("" : : "r"(v) : "memory");
}

static void parse_options(int argc, const char **argv, struct module_options *opts) {
    memset(opts, 0, sizeof(*opts));
    snprintf(opts->prompt, sizeof(opts->prompt), "OTP Code: ");

    for (int i = 0; i < argc; ++i) {
        if (!argv[i]) {
            continue;
        }
        if (strcmp(argv[i], "debug") == 0) {
            opts->debug = 1;
        } else if (strcmp(argv[i], "try_first_pass") == 0) {
            opts->try_first_pass = 1;
        } else if (strcmp(argv[i], "use_first_pass") == 0) {
            opts->use_first_pass = 1;
        } else if (strcmp(argv[i], "forward_pass") == 0) {
            opts->forward_pass = 1;
        } else if (strcmp(argv[i], "echo_code") == 0) {
            opts->echo_code = 1;
        } else if (strcmp(argv[i], "nodetect") == 0) {
            opts->nodetect = 1;
        } else if (strncmp(argv[i], "account=", 8) == 0) {
            snprintf(opts->account, sizeof(opts->account), "%s", argv[i] + 8);
        } else if (strncmp(argv[i], "socket_path=", 12) == 0) {
            snprintf(opts->socket_path, sizeof(opts->socket_path), "%s", argv[i] + 12);
        } else if (strncmp(argv[i], "prompt=", 7) == 0) {
            snprintf(opts->prompt, sizeof(opts->prompt), "%s", argv[i] + 7);
        }
    }
}

static int resolve_socket_path(const char *username, const struct module_options *opts, char *out_path, size_t out_len) {
    if (opts->socket_path[0] != '\0') {
        snprintf(out_path, out_len, "%s", opts->socket_path);
        return 0;
    }

    struct passwd *pw = getpwnam(username);
    if (!pw) {
        return -1;
    }

    char cand[UNIX_PATH_MAX];
    snprintf(cand, sizeof(cand), "/run/user/%u/otp-local.sock", (unsigned int)pw->pw_uid);
    struct stat st;
    if (stat(cand, &st) == 0 && S_ISSOCK(st.st_mode)) {
        snprintf(out_path, out_len, "%s", cand);
        return 0;
    }

    if (!opts->nodetect && pw->pw_dir && pw->pw_dir[0] != '\0') {
        snprintf(cand, sizeof(cand), "%s/.local/state/authy-local/otp-local.sock", pw->pw_dir);
        if (stat(cand, &st) == 0 && S_ISSOCK(st.st_mode)) {
            snprintf(out_path, out_len, "%s", cand);
            return 0;
        }
    }

    snprintf(out_path, out_len, "/run/user/%u/otp-local.sock", (unsigned int)pw->pw_uid);
    return 0;
}

static int prompt_code(pam_handle_t *pamh, const struct module_options *opts, char **out_code) {
    const struct pam_conv *conv = NULL;
    int rc = pam_get_item(pamh, PAM_CONV, (const void **)&conv);
    if (rc != PAM_SUCCESS || !conv || !conv->conv) {
        return PAM_CONV_ERR;
    }

    struct pam_message msg;
    const struct pam_message *msgp = &msg;
    struct pam_response *resp = NULL;

    msg.msg_style = opts->echo_code ? PAM_PROMPT_ECHO_ON : PAM_PROMPT_ECHO_OFF;
    msg.msg = (char *)opts->prompt;

    rc = conv->conv(1, &msgp, &resp, conv->appdata_ptr);
    if (rc != PAM_SUCCESS || !resp || !resp[0].resp) {
        if (resp) {
            if (resp[0].resp) {
                secure_zero(resp[0].resp, strlen(resp[0].resp));
                free(resp[0].resp);
            }
            free(resp);
        }
        return PAM_CONV_ERR;
    }

    *out_code = resp[0].resp;
    free(resp);
    return PAM_SUCCESS;
}

static int json_escape_string(const char *src, char *dst, size_t dst_len) {
    if (!src || !dst || dst_len == 0) {
        return -1;
    }
    size_t di = 0;
    for (size_t si = 0; src[si] != '\0'; ++si) {
        unsigned char c = (unsigned char)src[si];
        const char *esc = NULL;
        char buf[8];

        if (c == '"') {
            esc = "\\\"";
        } else if (c == '\\') {
            esc = "\\\\";
        } else if (c == '\b') {
            esc = "\\b";
        } else if (c == '\f') {
            esc = "\\f";
        } else if (c == '\n') {
            esc = "\\n";
        } else if (c == '\r') {
            esc = "\\r";
        } else if (c == '\t') {
            esc = "\\t";
        } else if (c < 0x20) {
            snprintf(buf, sizeof(buf), "\\u%04x", c);
            esc = buf;
        } else {
            buf[0] = (char)c;
            buf[1] = '\0';
            esc = buf;
        }

        size_t esc_len = strlen(esc);
        if (di + esc_len >= dst_len) {
            return -1;
        }
        memcpy(dst + di, esc, esc_len);
        di += esc_len;
    }
    dst[di] = '\0';
    return 0;
}

static int verify_with_daemon(const char *sock_path, const char *account, const char *code, int debug) {
    size_t path_len = strlen(sock_path);
    if (path_len == 0 || path_len >= sizeof(((struct sockaddr_un *)0)->sun_path)) {
        if (debug) {
            syslog(LOG_AUTH | LOG_DEBUG, "pam_otp_local: invalid socket path length");
        }
        return PAM_AUTHINFO_UNAVAIL;
    }

    int fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd < 0) {
        if (debug) {
            syslog(LOG_AUTH | LOG_DEBUG, "pam_otp_local: socket() failed: %s", strerror(errno));
        }
        return PAM_AUTHINFO_UNAVAIL;
    }

    struct timeval tv;
    tv.tv_sec = 3;
    tv.tv_usec = 0;
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));

    struct sockaddr_un addr;
    memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;
    memcpy(addr.sun_path, sock_path, path_len + 1);

    if (connect(fd, (struct sockaddr *)&addr, sizeof(addr)) != 0) {
        if (debug) {
            syslog(LOG_AUTH | LOG_DEBUG, "pam_otp_local: connect(%s) failed: %s", sock_path, strerror(errno));
        }
        close(fd);
        return PAM_AUTHINFO_UNAVAIL;
    }

    char esc_account[256];
    char esc_code[128];
    if (json_escape_string(account, esc_account, sizeof(esc_account)) != 0 ||
        json_escape_string(code, esc_code, sizeof(esc_code)) != 0) {
        if (debug) {
            syslog(LOG_AUTH | LOG_DEBUG, "pam_otp_local: failed to JSON-escape account or code");
        }
        secure_zero(esc_code, sizeof(esc_code));
        close(fd);
        return PAM_AUTH_ERR;
    }

    char req[1024];
    int req_len = snprintf(req, sizeof(req),
        "{\"action\":\"verify_totp\",\"account\":\"%s\",\"code\":\"%s\",\"format\":\"json\"}",
        esc_account, esc_code);
    secure_zero(esc_code, sizeof(esc_code));

    if (req_len < 0 || (size_t)req_len >= sizeof(req)) {
        if (debug) {
            syslog(LOG_AUTH | LOG_DEBUG, "pam_otp_local: request buffer overflow");
        }
        close(fd);
        return PAM_AUTH_ERR;
    }

    uint32_t net_len = htonl((uint32_t)req_len);
    if (write(fd, &net_len, 4) != 4 || write(fd, req, req_len) != req_len) {
        if (debug) {
            syslog(LOG_AUTH | LOG_DEBUG, "pam_otp_local: write failed: %s", strerror(errno));
        }
        secure_zero(req, sizeof(req));
        close(fd);
        return PAM_AUTHINFO_UNAVAIL;
    }
    secure_zero(req, sizeof(req));

    uint32_t resp_len_net = 0;
    ssize_t r = read(fd, &resp_len_net, 4);
    if (r != 4) {
        if (debug) {
            syslog(LOG_AUTH | LOG_DEBUG, "pam_otp_local: read length failed: %s", strerror(errno));
        }
        close(fd);
        return PAM_AUTHINFO_UNAVAIL;
    }

    uint32_t resp_len = ntohl(resp_len_net);
    if (resp_len == 0 || resp_len > 65536) {
        if (debug) {
            syslog(LOG_AUTH | LOG_DEBUG, "pam_otp_local: invalid response length: %u", (unsigned int)resp_len);
        }
        close(fd);
        return PAM_AUTHINFO_UNAVAIL;
    }

    char *resp_buf = malloc(resp_len + 1);
    if (!resp_buf) {
        close(fd);
        return PAM_AUTHINFO_UNAVAIL;
    }

    size_t total_read = 0;
    while (total_read < resp_len) {
        ssize_t n = read(fd, resp_buf + total_read, resp_len - total_read);
        if (n <= 0) {
            break;
        }
        total_read += n;
    }
    close(fd);

    if (total_read < resp_len) {
        if (debug) {
            syslog(LOG_AUTH | LOG_DEBUG, "pam_otp_local: short read from daemon");
        }
        free(resp_buf);
        return PAM_AUTHINFO_UNAVAIL;
    }
    resp_buf[resp_len] = '\0';

    if (debug) {
        syslog(LOG_AUTH | LOG_DEBUG, "pam_otp_local: daemon response: %s", resp_buf);
    }

    int auth_result = PAM_AUTH_ERR;
    if (strstr(resp_buf, "\"valid\": true") || strstr(resp_buf, "\"valid\":true")) {
        auth_result = PAM_SUCCESS;
    } else if (strstr(resp_buf, "\"status\": \"not_found\"") || strstr(resp_buf, "\"status\":\"not_found\"")) {
        auth_result = PAM_USER_UNKNOWN;
    } else {
        auth_result = PAM_AUTH_ERR;
    }

    secure_zero(resp_buf, resp_len);
    free(resp_buf);
    return auth_result;
}

PAM_EXTERN int pam_sm_authenticate(pam_handle_t *pamh, int flags, int argc, const char **argv) {
    (void)flags;
    struct module_options opts;
    parse_options(argc, argv, &opts);

    const char *user = NULL;
    int rc = pam_get_user(pamh, &user, NULL);
    if (rc != PAM_SUCCESS || !user || user[0] == '\0') {
        if (opts.debug) {
            syslog(LOG_AUTH | LOG_DEBUG, "pam_otp_local: cannot identify user");
        }
        return PAM_USER_UNKNOWN;
    }

    const char *target_account = opts.account[0] != '\0' ? opts.account : user;

    char sock_path[UNIX_PATH_MAX];
    if (resolve_socket_path(user, &opts, sock_path, sizeof(sock_path)) != 0) {
        if (opts.debug) {
            syslog(LOG_AUTH | LOG_DEBUG, "pam_otp_local: failed to resolve socket path");
        }
        return PAM_AUTHINFO_UNAVAIL;
    }

    char *code = NULL;
    int need_free_code = 0;

    if (opts.try_first_pass || opts.use_first_pass) {
        const void *authtok = NULL;
        if (pam_get_item(pamh, PAM_AUTHTOK, &authtok) == PAM_SUCCESS && authtok != NULL) {
            code = (char *)authtok;
        }
    }

    if (!code) {
        if (opts.use_first_pass) {
            return PAM_AUTH_ERR;
        }
        rc = prompt_code(pamh, &opts, &code);
        if (rc != PAM_SUCCESS || !code) {
            return rc;
        }
        need_free_code = 1;
    }

    rc = verify_with_daemon(sock_path, target_account, code, opts.debug);

    if (opts.forward_pass && rc == PAM_SUCCESS) {
        pam_set_item(pamh, PAM_AUTHTOK, code);
    }

    if (need_free_code && code) {
        secure_zero(code, strlen(code));
        free(code);
    }

    return rc;
}

PAM_EXTERN int pam_sm_setcred(pam_handle_t *pamh, int flags, int argc, const char **argv) {
    (void)pamh;
    (void)flags;
    (void)argc;
    (void)argv;
    return PAM_SUCCESS;
}
