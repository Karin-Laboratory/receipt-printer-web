CC ?= cc
PYTHON ?= python3
PKG_CONFIG ?= pkg-config
BUILD := build
CPPFLAGS += -Iinclude $(shell $(PKG_CONFIG) --cflags pappl)
CFLAGS ?= -O2 -g
CFLAGS += -std=c11 -Wall -Wextra -Werror -Wconversion -Wshadow
LDLIBS += $(shell $(PKG_CONFIG) --libs pappl) -pthread
SOURCES := $(filter-out src/pwg2pdf.c,$(wildcard src/*.c))

.PHONY: all clean test check-deps analyze check-capture-only
all: $(BUILD)/gateway $(BUILD)/pwg2pdf

check-deps:
	@$(PKG_CONFIG) --exists pappl || (echo "Install libpappl-dev" >&2; exit 1)
	@command -v pdftoppm >/dev/null || (echo "Install poppler-utils" >&2; exit 1)
	@command -v ipptool >/dev/null || (echo "Install cups-ipp-utils" >&2; exit 1)

$(BUILD):
	mkdir -p $@

$(BUILD)/gateway: $(SOURCES) include/gateway.h | $(BUILD)
	$(CC) $(CPPFLAGS) $(CFLAGS) $(SOURCES) -o $@ $(LDFLAGS) $(LDLIBS)

$(BUILD)/pwg2pdf: src/pwg2pdf.c | $(BUILD)
	$(CC) $(CFLAGS) $< -o $@ -lcups -lz

$(BUILD)/gateway-test: $(SOURCES) include/gateway.h | $(BUILD)
	$(CC) $(CPPFLAGS) $(CFLAGS) -DGW_TESTING $(SOURCES) -o $@ $(LDFLAGS) $(LDLIBS)

$(BUILD)/raster-fixture: tests/raster_fixture.c | $(BUILD)
	$(CC) $(CPPFLAGS) $(CFLAGS) $< -o $@ $(shell $(PKG_CONFIG) --libs pappl)

test: check-deps $(BUILD)/gateway $(BUILD)/gateway-test $(BUILD)/raster-fixture
	$(PYTHON) -m unittest discover -s tests -p 'test_*.py' -v

analyze: check-deps | $(BUILD)
	$(CC) $(CPPFLAGS) $(CFLAGS) -fanalyzer -fsyntax-only $(SOURCES)

check-capture-only:
	$(PYTHON) scripts/check_capture_only.py

clean:
	rm -rf $(BUILD)
