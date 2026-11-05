PREFIX ?= /usr
DESTDIR ?=
LIBDIR = $(DESTDIR)$(PREFIX)/lib/kantele
ICONDIR = $(DESTDIR)$(PREFIX)/share/icons/hicolor
SIZES = 16 22 24 32 48 64 128 256

.PHONY: all test install uninstall

all:

test:
	python3 -m unittest discover -s tests -v

install:
	install -d $(LIBDIR)/kantele/backends $(LIBDIR)/kantele/ui
	install -m 644 kantele/*.py $(LIBDIR)/kantele/
	install -m 644 kantele/backends/*.py $(LIBDIR)/kantele/backends/
	install -m 644 kantele/ui/*.py $(LIBDIR)/kantele/ui/
	install -Dm 755 kantele.sh $(DESTDIR)$(PREFIX)/bin/kantele
	install -Dm 755 kantele-shell $(DESTDIR)$(PREFIX)/bin/kantele-shell
	install -Dm 644 kantele.desktop $(DESTDIR)$(PREFIX)/share/applications/kantele.desktop
	for n in $(SIZES); do \
		install -Dm 644 assets/icons/kantele-$$n.png $(ICONDIR)/$${n}x$${n}/apps/kantele.png; \
	done
	install -Dm 644 assets/kantele.png $(ICONDIR)/512x512/apps/kantele.png

uninstall:
	rm -rf $(DESTDIR)$(PREFIX)/lib/kantele
	rm -f $(DESTDIR)$(PREFIX)/bin/kantele $(DESTDIR)$(PREFIX)/bin/kantele-shell $(DESTDIR)$(PREFIX)/share/applications/kantele.desktop
	for n in $(SIZES) 512; do rm -f $(ICONDIR)/$${n}x$${n}/apps/kantele.png; done
