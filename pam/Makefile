CC ?= gcc
CFLAGS ?= -Wall -Wextra -Werror -O2 -fPIC -fstack-protector-strong -D_FORTIFY_SOURCE=2
LDFLAGS ?= -shared -Wl,-z,relro,-z,now
LDLIBS ?= -lpam

DESTDIR ?=
PREFIX ?= /usr
PAM_DIR ?= $(DESTDIR)$(PREFIX)/lib/security

TARGET = pam_otp_local.so
SRCS = pam_otp_local.c
OBJS = $(SRCS:.c=.o)

all: $(TARGET)

$(TARGET): $(OBJS)
	$(CC) $(LDFLAGS) -o $@ $(OBJS) $(LDLIBS)

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

check: $(TARGET)
	@echo "Checking symbols in $(TARGET)..."
	nm -D --defined-only $(TARGET) | grep -E "pam_sm_authenticate|pam_sm_setcred"

install: $(TARGET)
	install -d $(PAM_DIR)
	install -m 0755 $(TARGET) $(PAM_DIR)/

clean:
	rm -f $(TARGET) $(OBJS)

.PHONY: all clean check install
