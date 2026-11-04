PREFIX ?= /usr
DESTDIR ?=
LIBDIR = $(DESTDIR)$(PREFIX)/lib/kantele

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
	install -Dm 644 kantele.desktop $(DESTDIR)$(PREFIX)/share/applications/kantele.desktop

uninstall:
	rm -rf $(DESTDIR)$(PREFIX)/lib/kantele
	rm -f $(DESTDIR)$(PREFIX)/bin/kantele $(DESTDIR)$(PREFIX)/share/applications/kantele.desktop
