"""Materialize synthetic service fixtures using only the Python standard library."""

import csv
import json
from io import StringIO
from itertools import permutations
from pathlib import Path

ITEM = ("SKU", "Quantity", "Name")
PRODUCT = ("SKU", "Unit price", "Stock", "Product name")
H = "SKU,Quantity,Name\n"
ROW = ("demo-a", "1", "Map")
CASES = {}


def csv_row(cells):
    out = StringIO(newline="")
    csv.writer(out, lineterminator="\r\n").writerow(cells)
    return out.getvalue()[:-2]


def sample(line, cells):
    return [line, *cells]


def saved(sku="DEMO-A", qty=1, label="Map", note="server default", active=True):
    return [sku, qty, label, note, active]


def add(
    slug,
    title,
    raw,
    *,
    rows=1,
    headers=ITEM,
    samples=(),
    issues=(),
    created=(),
    **options,
):
    assert slug not in CASES and title.isprintable() and len(title) < 72, title
    assert all(case["title"] != title for case in CASES.values()), title
    expected = dict(
        row_count=rows, headers=list(headers), sample=list(samples), issues=list(issues)
    )
    if "apply_issues" in options:
        expected["apply_issues"] = options.pop("apply_issues")
    if "insert_attempts" in options:
        expected["insert_attempts"] = options.pop("insert_attempts")
    expected["created"] = list(created)
    source = {"csv": raw} if isinstance(raw, str) else {"csv_hex": raw.hex(" ")}
    CASES[slug] = dict(title=title, **source, **options, expect=expected)


def rejected(slug, title, raw, code, line=None, *, message=None, **options):
    issue = [line, None, code]
    if message is not None:
        issue.append(message)
    add(slug, title, raw, rows=0, headers=(), issues=[issue], **options)


# Keep the input and expectation columns of the scenario tables together for review.
# fmt: off
def header_cases():
    for order in permutations(range(3)):
        headers = tuple(ITEM[i] for i in order)
        cells = tuple(ROW[i] for i in order)
        names = " ".join(headers)
        add(
            "headers-order-" + names.lower().replace(" ", "-"),
            f"Bind by header in {names} order",
            csv_row(headers) + "\n" + csv_row(cells),
            headers=headers, samples=[sample(2, cells)], created=[saved()],
        )
    for index, column in enumerate(ITEM):
        others = ITEM[:index] + ITEM[index + 1:]
        for suffix, headers, issues in (
            ("missing", others, [[1, column, "missing_header"]]),
            ("repeated", (*ITEM, column), [[1, column, "duplicate_header"]]),
            ("case-changed", (*others, column.lower()),
             [[1, None, "unknown_header"], [1, column, "missing_header"]]),
            ("padded", (*others, f" {column} "),
             [[1, None, "unknown_header"], [1, column, "missing_header"]]),
        ):
            add(f"headers-{column.lower()}-{suffix}", f"Reject {suffix} {column} header",
                csv_row(headers) + "\ndemo-a,1,Map", headers=(), issues=issues)

    for slug, title, header, line, errors in (
        ("only-sku", "Require both other headers when only SKU is present", "SKU", 1,
         [("Quantity", "missing_header"), ("Name", "missing_header")]),
        ("only-name", "Require SKU and Quantity when only Name is present", "Name", 1,
         [("SKU", "missing_header"), ("Quantity", "missing_header")]),
        ("only-quantity", "Require SKU and Name when only Quantity is present", "Quantity", 1,
         [("SKU", "missing_header"), ("Name", "missing_header")]),
        ("none-mapped", "Reject a header with no configured names", "Code,Count,Label", 1,
         [(None, "unknown_header"), *((c, "missing_header") for c in ITEM)]),
        ("empty-cell", "Report a trailing empty header cell", "SKU,Quantity,Name,", 1,
         [(None, "blank_header")]),
        ("tab-cell", "Treat a quoted tab header as blank", 'SKU,Quantity,"\t",Name', 1,
         [(None, "blank_header")]),
        ("unicode-space", "Treat an em-space header as blank", "SKU,Quantity,Name,\u2003", 1,
         [(None, "blank_header")]),
        ("blank-replaces-name", "Report blank and missing when Name is empty", 'SKU,Quantity,""', 1,
         [(None, "blank_header"), ("Name", "missing_header")]),
        ("all-blank", "Report a single blank issue for several empty headers", ",,", 1,
         [(None, "blank_header"), *((c, "missing_header") for c in ITEM)]),
        ("two-repeated", "Report repeated configured names in schema order", "Name,Name,SKU,SKU", 1,
         [("SKU", "duplicate_header"), ("Quantity", "missing_header"), ("Name", "duplicate_header")]),
        ("unknown-repeated", "Redact a repeated unknown header", "SKU,Quantity,Name,Alias,Alias", 1,
         [(None, "duplicate_header"), (None, "unknown_header")]),
        ("unknown-distinct", "Group distinct unexpected headers into one issue", "SKU,Quantity,Name,Alias,Tag", 1,
         [(None, "unknown_header")]),
        ("unknown-multiline", "Locate a multiline unknown header at its start", '\r\nSKU,Quantity,"Long\r\nName"', 2,
         [(None, "unknown_header"), ("Name", "missing_header")]),
        ("semicolon", "Do not infer a semicolon delimiter", "SKU;Quantity;Name", 1,
         [(None, "unknown_header"), *((c, "missing_header") for c in ITEM)]),
        ("tab-delimited", "Do not infer a tab delimiter", "SKU\tQuantity\tName", 1,
         [(None, "unknown_header"), *((c, "missing_header") for c in ITEM)]),
        ("note-not-allowed", "Reject an unmapped model field as a CSV header", "SKU,Quantity,Name,internal_note", 1,
         [(None, "unknown_header")]),
    ):
        messages = {"unknown_header": "CSV contains unexpected headers."}
        add(f"headers-{slug}", title, header + "\ndemo-a,one,Map", headers=(), issues=[
            [line, col, code, messages[code]] if code in messages else [line, col, code]
            for col, code in errors
        ])


def text_cases():
    for slug, title, value, cleaned in (
        ("comma", "Preserve a comma in a quoted label", "Map, folded", "Map, folded"),
        ("quote", "Unescape doubled double quotes in a label", 'Map "A"', 'Map "A"'),
        ("only-quote", "Decode a cell containing only a double quote", '"', '"'),
        ("only-comma", "Decode a cell containing only a comma", ",", ","),
        ("apostrophe", "Treat apostrophes as label text", "Maker's map", "Maker's map"),
        ("backslash", "Preserve a literal backslash in label text", "Map\\Index", "Map\\Index"),
        ("inner-tabs", "Keep interior tabs after Django trims edges", "\tTrail\tMap\t", "Trail\tMap"),
        ("spaces", "Preview original padding but save a trimmed label", "  Map  ", "Map"),
        ("unicode-spaces", "Trim Unicode whitespace only in the saved label", "\u00a0Map\u2003", "Map"),
        ("accent", "Round-trip precomposed accented text", "Café", "Café"),
        ("combining", "Preserve decomposed text without normalization", "Cafe\u0301", "Cafe\u0301"),
        ("cjk", "Round-trip CJK label text", "地図", "地図"),
        ("emoji", "Round-trip a four-byte Unicode label character", "Map 🧭", "Map 🧭"),
        ("embedded-bom", "Keep a BOM inside a data cell", "Trail\ufeffMap", "Trail\ufeffMap"),
        ("embedded-lf", "Preserve LF inside a quoted label", "Trail\nMap", "Trail\nMap"),
        ("embedded-cr", "Preserve bare CR inside a quoted label", "Trail\rMap", "Trail\rMap"),
        ("embedded-crlf", "Preserve CRLF inside a quoted label", "Trail\r\nMap", "Trail\r\nMap"),
        ("embedded-blank", "Keep a blank physical line inside a label", "Trail\n\nMap", "Trail\n\nMap"),
        ("embedded-ends", "Trim multiline cell edges after raw preview", "\nTrail Map\r\n", "Trail Map"),
    ):
        cells = (*ROW[:2], value)
        add(f"text-{slug}", title, H + csv_row(cells), samples=[sample(2, cells)],
            created=[saved(label=cleaned)])

    for slug, title, raw, count, samples, issues in (
        ("leading-blanks", "Skip leading LF blanks before the header", "\n\n" + H + "demo-a,1,Map", 1,
         [[4, *ROW]], []),
        ("cr-records", "Count records separated only by bare CR", "SKU,Quantity,Name\rdemo-a,1,Map\r", 1,
         [[2, *ROW]], []),
        ("quoted-header", "Bind quoted headers with a leading UTF-8 BOM", '\ufeff"SKU","Quantity","Name"\r\ndemo-a,1,Map',
         1, [[2, *ROW]], []),
        ("mixed-endings", "Locate rows across CRLF, CR, and LF separators", "SKU,Quantity,Name\r\n\rdemo-a,1,Map\n\n",
         1, [[3, *ROW]], []),
        ("short-after-multiline", "Locate a short row after a multiline record", H + 'demo-a,1,"Trail\nMap"\nshort,2',
         2, [[2, "demo-a", "1", "Trail\nMap"]], [[4, None, "row_width"]]),
        ("long-after-blank", "Count a trailing comma as an extra cell", H + "\ndemo-a,1,Map,", 1, [],
         [[3, None, "row_width"]]),
        ("quoted-empty-record", "Count a quoted empty record instead of skipping it", H + '\n""\n', 1, [],
         [[3, None, "row_width"]]),
        ("spaces-record", "Treat a space-only physical row as a record", H + " \t\n", 1, [], [[2, None, "row_width"]]),
        ("multiline-short", "Report a multiline short record at its start", H + '\n"Trail\nMap",5\n', 1, [],
         [[3, None, "row_width"]]),
        ("multiline-long", "Report a multiline wide record at its start", H + 'demo-a,1,"Trail\nMap",Extra', 1, [],
         [[2, None, "row_width"]]),
        ("recovery", "Keep a valid record after malformed-width records", H + 'only\n\n"a\nb",1,2,3\ndemo-a,1,Map',
         3, [[6, *ROW]], [[2, None, "row_width"], [4, None, "row_width"]]),
    ):
        add(f"text-{slug}", title, raw, rows=count, samples=samples, issues=issues,
            created=[] if issues else [saved()])

    for slug, title, raw, code, line in (
        ("zero-bytes", "Reject an upload containing zero bytes", "", "empty", None),
        ("blank-lines", "Reject an upload containing only physical blank lines", "\r\n\r\n", "empty", None),
        ("bom-only", "Treat a standalone BOM as an empty upload", "\ufeff", "empty", None),
        ("header-only", "Reject a header without a data record", H.rstrip(), "no_rows", None),
        ("header-plus-blanks", "Do not count trailing newline records after the header", H + "\r\n\n", "no_rows", None),
        ("unclosed", "Reject an unclosed quote starting on line two", H + 'demo-a,1,"Trail\nMap', "csv", 2),
        ("characters-after-quote", "Reject characters after a closed quoted cell", H + 'demo-a,1,"Map"x', "csv", 2),
        ("bad-quote-after-good", "Discard earlier samples when a later quote cannot close",
         H + 'demo-a,1,Map\n\ndemo-b,2,"Lantern', "csv", 4),
        ("bad-quote-header", "Locate an unclosed header after a leading blank", '\n"SKU,Quantity,Name', "csv", 2),
        ("nul-header", "Reject NUL in a header before binding", "SK\0U,Quantity,Name\ndemo-a,1,Map", "nul", None),
        ("nul-quoted", "Reject NUL inside a quoted field", H + 'demo-a,1,"Trail\0Map"', "nul", None),
        ("nul-after-good", "Reject NUL even after an otherwise valid row", H + "demo-a,1,Map\n\0", "nul", None),
        ("latin1", "Reject a Latin-1 byte in a label", H.encode() + b"demo-a,1,Caf\xe9", "encoding", None),
        ("incomplete-utf8", "Reject a truncated UTF-8 code point at EOF", H.encode() + b"demo-a,1,\xf0\x9f", "encoding", None),
        ("continuation-byte", "Reject an orphaned UTF-8 continuation byte", b"\x80" + H.encode(), "encoding", None),
        ("utf16-bom", "Reject UTF-16 despite its byte-order marker", b"\xff\xfe" + (H + "demo-a,1,Map").encode(
            "utf-16-le"), "encoding", None),
    ):
        rejected(f"text-{slug}", title, raw, code, line)


def limit_cases():
    for slug, name, raw, label in (
        ("ascii-eof", "ASCII without a final newline", H + "demo-a,1,Map", "Map"),
        ("crlf", "a CRLF upload", H.replace("\n", "\r\n") + "demo-a,1,Map\r\n", "Map"),
        ("bom", "the UTF-8 BOM", "\ufeff" + H + "demo-a,1,Map", "Map"),
        ("accent", "a two-byte accent", H + "demo-a,1,Café", "Café"),
        ("cjk", "three-byte CJK text", H + "demo-a,1,地図", "地図"),
        ("emoji", "a four-byte emoji", H + "demo-a,1,🧭", "🧭"),
        ("quoted", "CSV quote escapes", H + 'demo-a,1,"""Map"""', '"Map"'),
        ("multiline", "an embedded line break", H + 'demo-a,1,"Trail\nMap"', "Trail\nMap"),
    ):
        size = len(raw.encode())
        add(f"limits-bytes-{slug}-exact", f"Allow exactly the byte cap with {name}", raw,
            limits={"max_bytes": size}, samples=[[2, "demo-a", "1", label]], created=[saved(label=label)])
        rejected(f"limits-bytes-{slug}-over", f"Count {name} toward byte overflow", raw,
                 "too_large", limits={"max_bytes": size - 1})

    for slug, name, label, size in (
        ("ascii", "an ASCII label", "Trail Map", 9),
        ("unicode", "multibyte characters", "地図é🧭地図é🧭界", 9),
        ("combining", "combining marks separately", "Cafe\u0301WXYZ", 9),
        ("comma", "a quoted comma", "Map, fold", 9),
        ("doubled-quote", "one decoded quote", 'Map "Wide"', 10),
        ("crlf", "both characters of embedded CRLF", "First\r\nLast", 11),
        ("padding", "padding before Django trims it", "   Map   ", 9),
    ):
        cells = (*ROW[:2], label)
        raw = H + csv_row(cells)
        add(f"limits-cell-{slug}-exact", f"Allow the exact character cap with {name}", raw,
            limits={"max_cell_chars": size}, samples=[sample(2, cells)], created=[saved(label=label.strip())])
        rejected(f"limits-cell-{slug}-over", f"Count {name} toward cell overflow", raw,
                 "cell_too_long", 2, limits={"max_cell_chars": size - 1},
                 message=f"Cell 3 exceeds {size - 1} characters.")

    add("limits-rows-exact", "Count only logical rows, not blanks or quoted newlines",
        H + '\n' + 'demo-a,1,"Trail\nMap"\n\ndemo-b,2,Lamp\n\n', rows=2, limits={"max_rows": 2},
        samples=[[3, "demo-a", "1", "Trail\nMap"], [6, "demo-b", "2", "Lamp"]],
        created=[saved(label="Trail\nMap"), saved("DEMO-B", 2, "Lamp")])
    for slug, title, raw, limit, line in (
        ("later-record", "Locate row overflow after a multiline record", H + 'demo-a,1,"Trail\nMap"\n\ndemo-b,2,Lamp',
         {"max_rows": 1}, 5),
        ("empty-quoted", "Count a quoted empty row toward row overflow", H + 'demo-a,1,Map\n\n""', {"max_rows": 1}, 4),
        ("wrong-width", "Count short records before width validation", H + 'demo-a,1\ndemo-b,2,Lamp', {"max_rows": 1}, 3),
        ("before-cell", "Report row overflow before scanning excess cells", H + 'demo-a,1,Map\ndemo-b,2,Longer than cap',
         {"max_rows": 1, "max_cell_chars": 8}, 3),
    ):
        rejected(f"limits-rows-{slug}", title, raw, "too_many_rows", line, limits=limit)
    rejected("limits-header-over", "Enforce the character cap on the header", "\n" + H + "demo-a,1,Map",
             "cell_too_long", 2, limits={"max_cell_chars": 7}, message="Cell 2 exceeds 7 characters.")
    rejected("limits-header-before-binding", "Check oversized headers before testing allowed names",
             'SKU,Quantity,"Unmapped\nHeading"\ndemo-a,1,Map', "cell_too_long", 1,
             limits={"max_cell_chars": 8}, message="Cell 3 exceeds 8 characters.")
    rejected("limits-first-oversized", "Report the leftmost oversized cell in a record",
             H + "DEMO-LONG,123456789,Long label", "cell_too_long", 2,
             limits={"max_cell_chars": 8}, message="Cell 1 exceeds 8 characters.")
    rejected("limits-byte-before-decode", "Reject excess bytes before attempting UTF-8 decode",
             H.encode() + b"\xff", "too_large", limits={"max_bytes": len(H)})
    rejected("limits-quantity-before-width", "Check an oversized cell before testing row width",
             H + "demo-a,123456789", "cell_too_long", 2,
             limits={"max_cell_chars": 8}, message="Cell 2 exceeds 8 characters.")


def item_cases():
    for slug, name, sku, cleaned, code in (
        ("lowercase", "mixed-case SKU", "demo-MaP", "DEMO-MAP", None),
        ("padding", "padded SKU", " demo-a\t", "DEMO-A", None),
        ("accent", "accented SKU", "demo-café", "DEMO-CAFÉ", None),
        ("length-exact", "SKU at maximum length", "demo-1234567", "DEMO-1234567", None),
        ("length-over", "SKU beyond maximum length", "DEMO-12345678", None, "max_length"),
        ("missing", "empty SKU", "", None, "required"),
        ("whitespace", "whitespace-only SKU", " \t", None, "required"),
        ("no-dash", "SKU without the prefix separator", "DEMOMAP", None, "sku_prefix"),
        ("different-prefix", "SKU with a different prefix", "SAMPLE-MAP", None, "sku_prefix"),
        ("uppercase-expansion", "SKU expanded beyond field length by uppercasing", "demo-123456ß", None, "max_length"),
    ):
        cells = (sku, "1", "Map")
        add(f"item-sku-{slug}", f"{'Reject' if code else 'Clean'} {name}", H + csv_row(cells),
            samples=[] if code else [sample(2, cells)], issues=[[2, "SKU", code]] if code else [],
            created=[] if code else [saved(sku=cleaned)])

    for slug, name, raw, value, code in (
        ("zero", "zero quantity", "0", 0, None),
        ("zero-padded", "zero-padded quantity", "0042", 42, None),
        ("whitespace", "quantity padded with whitespace", " 7\t", 7, None),
        ("positive-sign", "a signed positive quantity", "+3", 3, None),
        ("negative-zero", "negative zero as an integer", "-0", 0, None),
        ("integral-decimal", "an integer with trailing decimal zeros", "3.00", 3, None),
        ("unicode-digits", "Unicode decimal digits as a quantity", "１２", 12, None),
        ("max", "the exact model quantity ceiling", "500", 500, None),
        ("above-max", "quantity one past the model ceiling", "501", None, "invalid"),
        ("negative", "a negative quantity", "-1", None, "min_value"),
        ("fraction", "a fractional quantity", "1.25", None, "invalid"),
        ("scientific", "exponent notation for integer quantity", "1e2", None, "invalid"),
        ("grouping", "a quoted quantity with a grouping comma", "1,000", None, "invalid"),
        ("missing", "a missing quantity", "", None, "required"),
        ("only-spaces", "a whitespace-only quantity", " \t", None, "invalid"),
        ("word", "a textual quantity", "one", None, "invalid"),
        ("infinity", "an infinite quantity", "Infinity", None, "invalid"),
        ("huge", "quantity beyond the database integer range", "9223372036854775808", None, "max_value"),
    ):
        cells = ("demo-a", raw, "Map")
        column = None if slug == "above-max" else "Quantity"
        add(f"item-quantity-{slug}", f"{'Reject' if code else 'Accept'} {name}", H + csv_row(cells),
            samples=[] if code else [sample(2, cells)], issues=[[2, column, code]] if code else [],
            created=[] if code else [saved(qty=value)])

    for slug, name, label, cleaned, code in (
        ("length-exact", "label at exactly 40 characters", "M" * 40, "M" * 40, None),
        ("length-over", "label with 41 characters", "M" * 41, None, "max_length"),
        ("unicode-length", "40 multibyte characters in the model label", "界" * 40, "界" * 40, None),
        ("trimmed-length", "label whose padding is trimmed before length check", " " + "M" * 40, "M" * 40, None),
        ("missing", "an empty label", "", None, "required"),
        ("spaces", "a whitespace-only label", " \t\u2003", None, "required"),
        ("reserved-padded", "the reserved name after case folding and trim", " reSERVed ", None, "reserved_name"),
        ("reserved-neighbor", "a label containing but not equal to Reserved", "Reserved map", "Reserved map", None),
    ):
        cells = (*ROW[:2], label)
        column = None if code == "reserved_name" else "Name"
        add(f"item-label-{slug}", f"{'Reject' if code else 'Accept'} {name}", H + csv_row(cells),
            samples=[] if code else [sample(2, cells)], issues=[[2, column, code]] if code else [],
            created=[] if code else [saved(label=cleaned)])

    add("item-errors-across-rows", "Preserve field issue order and physical lines across rows",
        H + 'bad,word,\n\ndemo-ok,2,"Trail\nMap"\ndemo-z,501,Reserved', rows=3,
        samples=[[4, "demo-ok", "2", "Trail\nMap"]], issues=[
            [2, "SKU", "sku_prefix"], [2, "Quantity", "invalid"], [2, "Name", "required"],
            [6, None, "reserved_name"], [6, None, "invalid"],
        ])
    add("item-errors-reordered", "Attach form errors to headers despite reordered input",
        'Name,SKU,Quantity\n"\n",bad,wrong', headers=("Name", "SKU", "Quantity"),
        issues=[[2, "SKU", "sku_prefix"], [2, "Quantity", "invalid"], [2, "Name", "required"]])


def product_cases():
    # Input spellings, expected database values, or expected Django validation codes.
    prices = (
        ("zero", "a zero price", "0", "0.00", None),
        ("one-place", "a one-place price", "4.2", "4.20", None),
        ("exact", "a two-place price", "4.25", "4.25", None),
        ("leading-point", "price without a leading zero", ".25", "0.25", None),
        ("trailing-point", "a price with a trailing point", "4.", "4.00", None),
        ("whitespace", "a whitespace-padded price", " 4.25\t", "4.25", None),
        ("plus", "a price with an explicit plus sign", "+4.25", "4.25", None),
        ("negative-zero", "negative zero as a price", "-0.00", "0.00", None),
        ("exponent", "scientific price notation at two places", "425E-2", "4.25", None),
        ("unicode", "Unicode decimal digits in price", "４.２５", "4.25", None),
        ("max", "the price at both decimal digit limits", "999999.99", "999999.99", None),
        ("negative", "the stock item's negative price", "-0.01", None, "min_value"),
        ("max-digits", "price with too many total digits", "1000000.00", None, "max_digits"),
        ("whole-digits", "price with too many whole digits", "1000000", None, "max_whole_digits"),
        ("decimal-places", "price with three nonzero decimal places", "1.001", None, "max_decimal_places"),
        ("trailing-zero", "extra decimal place even when the digit is zero", "1.230", None, "max_decimal_places"),
        ("nan", "NaN as a price", "NaN", None, "invalid"),
        ("infinity", "infinity as a price", "Infinity", None, "invalid"),
        ("decimal-comma", "a quoted decimal-comma price", "4,25", None, "invalid"),
        ("currency", "a currency symbol in price", "$4.25", None, "invalid"),
        ("empty", "missing price", "", None, "required"),
        ("blank", "a whitespace-only price", " \t", None, "invalid"),
    )
    stocks = (
        ("zero", "zero stock", "0", 0, None),
        ("negative", "negative stock", "-1", None, "min_value"),
        ("trim", "space-padded stock", " 03 ", 3, None),
        ("fraction", "fractional stock", "1.5", None, "invalid"),
        ("decimal-zeros", "an integral stock value with decimal zeros", "1.0", 1, None),
        ("scientific", "scientific notation in stock", "3e1", None, "invalid"),
        ("signed", "stock with an explicit plus sign", "+1", 1, None),
        ("max", "stock at the portable signed integer limit", "2147483647", 2147483647, None),
        ("missing", "empty stock", "", None, "required"),
        ("grouping", "stock with a thousands separator", "2,000", None, "invalid"),
    )
    names_and_skus = (
        ("sku-required", "an empty product SKU", "", None, "SKU", "required"),
        ("sku-prefix", "an incorrect product SKU prefix", "ITEM-MAP", None, "SKU", "demo_sku"),
        ("sku-max", "the example product's longer SKU limit", "demo-123456789012345", "DEMO-123456789012345", "SKU", None),
        ("sku-over", "a product SKU beyond 20 characters", "demo-1234567890123456", None, "SKU", "max_length"),
        ("name-max", "a product name of exactly 100 characters", "界" * 100, "界" * 100, "Product name", None),
        ("name-over", "a product name beyond 100 characters", "界" * 101, None, "Product name", "max_length"),
        ("name-required", "a blank product name after stripping", " \t", None, "Product name", "required"),
        ("name-reserved", "the name Reserved on the real Product model", "Reserved", "Reserved", "Product name", None),
    )

    def product(slug, title, cells, stored, column, code):
        add(f"product-{slug}", f"{'Reject' if code else 'Accept'} {title}",
            csv_row(PRODUCT) + "\n" + csv_row(cells), profile="product", headers=PRODUCT,
            samples=[] if code else [sample(2, cells)], issues=[[2, column, code]] if code else [],
            created=[] if code else [stored])

    for slug, title, raw, value, code in prices:
        product("price-" + slug, title, ("demo-p", raw, "1", "Map"), ["DEMO-P", value, 1, "Map"], "Unit price", code)
    for slug, title, raw, value, code in stocks:
        product("stock-" + slug, title, ("demo-p", "4.25", raw, "Map"), ["DEMO-P", "4.25", value, "Map"], "Stock", code)
    for slug, title, raw, value, column, code in names_and_skus:
        cells = (raw, "4.25", "1", "Map") if column == "SKU" else ("demo-p", "4.25", "1", raw)
        stored = [value, "4.25", 1, "Map"] if column == "SKU" else ["DEMO-P", "4.25", 1, value]
        product(slug, title, cells, stored, column, code)


def mapping_cases():
    for slug, title, headers, actual, line, cells, issue in (
        ("translated", "Bind configured non-ASCII header names", ("Código", "数量", "Título"), None, 2, ROW, None),
        ("comma", "Bind a configured header containing a comma", ("Item, code", "Count", "Label"), None, 2, ROW, None),
        ("quote", "Bind a configured header containing a double quote", ('Item "code"', "Count", "Label"), None, 2, ROW, None),
        ("newline", "Start data on line three after a mapped multiline header", ("Item\ncode", "Count", "Label"), None, 3, ROW, None),
        ("spaces", "Bind an alias with configured surrounding spaces", ("  Code  ", "Count", "Label"), None, 2, ROW, None),
        ("no-normalization", "Reject a decomposed spelling of an accented alias", ("Café", "Count", "Label"),
         ("Cafe\u0301", "Count", "Label"), 2, ROW, [[1, None, "unknown_header"], [1, "Café", "missing_header"]]),
        ("bad-count", "Report invalid input using the configured quantity alias", ("Code", "Items", "Label"), None,
         2, ("demo-a", "many", "Map"), [[2, "Items", "invalid"]]),
        ("old-name", "Reject an original header once an alias replaces it", ("Code", "Count", "Label"),
         ("SKU", "Count", "Label"), 2, ROW, [[1, None, "unknown_header"], [1, "Code", "missing_header"]]),
    ):
        add(f"mapping-alias-{slug}", title, csv_row(actual or headers) + "\n" + csv_row(cells),
            columns=dict(zip(headers, ("sku", "quantity", "label"), strict=True)), headers=() if actual else headers,
            samples=[] if issue else [sample(line, cells)], issues=issue or [], created=[] if issue else [saved()])

    for slug, title, note, cleaned, code in (
        ("override", "Set the server-defaulted field when explicitly mapped", "Reviewed", "Reviewed", None),
        ("trim", "Trim mapped note edges only on save", "  Reviewed  ", "Reviewed", None),
        ("empty", "Require an explicitly mapped note when its cell is empty", "", None, "required"),
        ("spaces", "Do not treat blank mapped notes as omitted fields", "\t ", None, "required"),
        ("max", "Save a mapped note at its model field length limit", "N" * 40, "N" * 40, None),
        ("over", "Report note character overflow at its mapped header", "界" * 41, None, "max_length"),
        ("multiline", "Save multiline note text through the optional mapping", "One\r\nTwo", "One\r\nTwo", None),
    ):
        cells = (*ROW, note)
        add(f"mapping-note-{slug}", title, "SKU,Quantity,Name,Note\n" + csv_row(cells),
            profile="note", headers=(*ITEM, "Note"), samples=[] if code else [sample(2, cells)],
            issues=[[2, "Note", code]] if code else [], created=[] if code else [saved(note=cleaned)])
    add("mapping-note-missing-header", "A mapped note header cannot be left out of the CSV", H + csv_row(ROW),
        profile="note", headers=(), issues=[[1, "Note", "missing_header"]])

    for slug, title, value, cleaned, code in (
        ("yes", "Coerce the configured yes choice to True", "yes", True, None),
        ("no", "Coerce the configured no choice to False", "no", False, None),
        ("case", "Reject a capitalized boolean choice not on the allowlist", "Yes", None, "invalid_choice"),
        ("number", "Do not interpret 1 as a configured boolean choice", "1", None, "invalid_choice"),
        ("padding", "Require exact text for a typed boolean choice", " yes ", None, "invalid_choice"),
        ("missing", "Require a value when the mapped choice is empty", "", None, "required"),
    ):
        cells = (value, *ROW)
        add(f"mapping-active-{slug}", title, "Active,SKU,Quantity,Name\n" + csv_row(cells), profile="active",
            headers=("Active", *ITEM), samples=[] if code else [sample(2, cells)],
            issues=[[2, "Active", code]] if code else [], created=[] if code else [saved(active=cleaned)])

    for slug, title, raw, rows, samples, created, issues in (
        ("null", "Save a quoted empty optional integer as NULL", '""', 1, [[2, ""]], [[1001, None]], []),
        ("zero", "Keep zero distinct from an omitted optional integer", '""\n0', 2,
         [[2, ""], [3, "0"]], [[1001, None], [1001, 0]], []),
        ("many-null", "Allow multiple NULL slots for the same default parent", '""\n\n""', 2,
         [[2, ""], [4, ""]], [[1001, None], [1001, None]], []),
        ("negative", "Validate a nonempty optional integer against its minimum", '""\n-1', 2,
         [[2, ""]], [], [[3, "Slot", "min_value"]]),
        ("space", "Reject spaces as a nonempty optional integer", ' \t', 1, [], [], [[2, "Slot", "invalid"]]),
    ):
        add(f"mapping-placement-{slug}", title, "Slot\n" + raw, profile="placement", headers=("Slot",), rows=rows,
            samples=samples, created=created, issues=issues)
# fmt: on


def duplicate(line, first, *columns):
    return [
        line,
        columns[0] if len(columns) == 1 else None,
        "duplicate_row",
        f"Duplicate value for {', '.join(columns)}; first seen on line {first}.",
    ]


def table(
    slug, title, records, *, lines=None, headers=ITEM, valid=None, gap="\n", **options
):
    # For records with embedded newlines or blank separators, callers supply the physical lines.
    if lines is None:
        lines = range(2, len(records) + 2)
    samples = [sample(line, cells) for line, cells in zip(lines, records, strict=True)]
    if valid is not None:
        samples = [samples[i] for i in valid]
    add(
        slug,
        title,
        csv_row(headers) + "\n" + gap.join(map(csv_row, records)),
        rows=len(records),
        headers=headers,
        samples=samples[:10],
        **options,
    )


# fmt: off
def uniqueness_cases():
    for slug, title, left, right in (
        ("exact", "Reject exact SKU repeats with different other fields", "DEMO-A", "DEMO-A"),
        ("case", "Compare SKUs after case cleaning, not raw text", "demo-a", "DEMO-A"),
        ("spaces", "Compare SKUs after trimming surrounding whitespace", "  DEMO-A\t", "DEMO-A"),
        ("accent", "Compare SKUs after Unicode uppercase conversion", "demo-café", "DEMO-CAFÉ"),
        ("sharp-s", "Detect a cleaned SKU collision after uppercase expansion", "demo-ß", "DEMO-SS"),
        ("sigma", "Compare both Greek lowercase sigma variants as one SKU", "demo-ς", "demo-σ"),
    ):
        table(f"unique-sku-{slug}", title, [(left, "1", "Map"), (right, "2", "Lamp")], valid=[0],
              issues=[duplicate(3, 2, "SKU")])

    for slug, title, left, right, l_clean, r_clean in (
        ("accent-distinct", "Keep accented and unaccented SKUs distinct", "demo-é", "demo-e", "DEMO-É", "DEMO-E"),
        ("normalization", "Do not normalize canonically equivalent SKU strings", "demo-é", "demo-e\u0301", "DEMO-É", "DEMO-E\u0301"),
        ("inner-space", "Do not collapse interior whitespace in SKU keys", "demo-a b", "demo-ab", "DEMO-A B", "DEMO-AB"),
        ("suffix", "Allow distinct SKU keys that share a prefix", "demo-a", "demo-ab", "DEMO-A", "DEMO-AB"),
    ):
        table(f"unique-sku-{slug}", title, [(left, "1", "Map"), (right, "2", "Lamp")],
              created=[saved(l_clean), saved(r_clean, 2, "Lamp")])

    for slug, title, qty, other_qty, label, other_label in (
        ("exact", "Reject repeat of exact label and quantity with a new SKU", "1", "1", "Map", "Map"),
        ("padding", "Compare trimmed labels in composite uniqueness keys", "1", "1", " Map ", "Map"),
        ("leading-zero", "Compare zero-padded integers in composite keys", "01", "1", "Map", "Map"),
        ("decimal-zero", "Compare integral decimals in composite uniqueness keys", "1.00", "1", "Map", "Map"),
        ("negative-zero", "Match negative and positive zero in composite keys", "-0", "0", "Map", "Map"),
        ("unicode-number", "Match Unicode and ASCII digits in composite keys", "１", "1", "Map", "Map"),
        ("comma-text", "Compare decoded label values containing a comma", "1", "1", "Map, folded", "Map, folded"),
    ):
        table(f"unique-pair-{slug}", title, [("demo-a", qty, label), ("demo-b", other_qty, other_label)],
              valid=[0], issues=[duplicate(3, 2, "Name", "Quantity")])

    for slug, title, other_qty, other_label in (
        ("different-quantity", "Allow the same label with a different quantity", 2, "Map"),
        ("different-label", "Allow a repeated quantity with a different label", 1, "Lamp"),
        ("label-case", "Keep case differences in composite label keys", 1, "map"),
    ):
        table(f"unique-pair-{slug}", title, [ROW, ("demo-b", str(other_qty), other_label)],
              created=[saved(), saved("DEMO-B", other_qty, other_label)])

    table("unique-both-same-row", "Report both unique groups when one prior row matches both",
          [ROW, ("DEMO-A", "01", "Map")], valid=[0],
          issues=[duplicate(3, 2, "SKU"), duplicate(3, 2, "Name", "Quantity")])
    table("unique-both-different-rows", "Point to different prior rows for the two duplicate keys",
          [ROW, ("demo-b", "2", "Lamp"), ("DEMO-A", "2", "Lamp")], valid=[0, 1],
          issues=[duplicate(4, 2, "SKU"), duplicate(4, 3, "Name", "Quantity")])
    table("unique-first-seen-across-blanks", "Cite the earliest occurrence across later repeats and blanks",
          [ROW, ("DEMO-A", "2", "Lamp"), ("DEMO-A", "3", "Trail")], gap="\n\n", lines=[2, 4, 6],
          valid=[0], issues=[duplicate(4, 2, "SKU"), duplicate(6, 2, "SKU")])
    table("unique-first-seen-multiline", "Cite the start of a multiline duplicate and its first record",
          [("demo-a", "1", "Trail\nMap"), ("demo-b", "1", "Trail\nMap")], lines=[2, 4],
          valid=[0], issues=[duplicate(4, 2, "Name", "Quantity")])
    table("unique-invalid-sku-key", "Do not reserve a SKU from a row that fails field validation",
          [("demo-a", "wrong", "Lamp"), ROW], valid=[1], issues=[[2, "Quantity", "invalid"]])
    table("unique-invalid-composite-key", "Do not reserve a label pair from an invalid form",
          [("wrong", "1", "Map"), ROW], valid=[1], issues=[[2, "SKU", "sku_prefix"]])
    table("unique-invalid-later", "Validate a bad row before checking its repeated SKU",
          [ROW, ("demo-a", "2", "Reserved")], valid=[0], issues=[[3, None, "reserved_name"]])
    table("unique-aliases", "Use mapped CSV aliases when naming duplicate keys",
          [ROW, ("DEMO-A", "01", "Map")], headers=("Code", "Count", "Label"),
          columns={"Code": "sku", "Count": "quantity", "Label": "label"}, valid=[0],
          issues=[duplicate(3, 2, "Code"), duplicate(3, 2, "Label", "Count")])
    table("unique-product-only-sku", "Allow repeated product names, prices, and stock with new SKUs",
          [("demo-a", "1", "1", "Map"), ("demo-b", "1.00", "1", "Map")], headers=PRODUCT, profile="product",
          created=[["DEMO-A", "1.00", 1, "Map"], ["DEMO-B", "1.00", 1, "Map"]])
    table("unique-product-sku", "Detect cleaned SKU repeats on the example product model",
          [("demo-a", "1", "1", "Map"), (" DEMO-A ", "2", "2", "Lamp")], headers=PRODUCT, profile="product",
          valid=[0], issues=[duplicate(3, 2, "SKU")])


def preview_cases():
    # Numbered quantities make each row distinct under the composite uniqueness rule.
    records = [(f"demo-{i}", str(i), "Map") for i in range(1, 13)]
    created = [saved(f"DEMO-{i}", i) for i in range(1, 13)]
    for count, label in ((9, "below"), (10, "at"), (11, "above")):
        table(f"preview-cap-{label}", f"Return the ordered sample {label} the ten-row preview cap",
              records[:count], created=created[:count])
    table("preview-invalid-first", "Fill the sample with valid rows after an invalid first row",
          [("bad", "1", "Lamp"), *records[:10]], valid=range(1, 11), issues=[[2, "SKU", "sku_prefix"]])
    table("preview-invalid-middle", "Keep ten valid samples when an invalid row is in the middle",
          [*records[:5], ("demo-bad", "?", "Map"), *records[5:11]],
          valid=[*range(5), *range(6, 12)], issues=[[7, "Quantity", "invalid"]])
    table("preview-invalid-after-cap", "Validate rows even beyond the preview sample cap",
          [*records[:10], ("demo-bad", "-1", "Map"), records[10]],
          valid=[*range(10), 11], issues=[[12, "Quantity", "min_value"]], insert_attempts=0)
    table("preview-duplicate-after-cap", "Check duplicates that both fall outside the preview sample",
          [*records, ("DEMO-11", "0", "Lamp")], valid=range(12),
          issues=[duplicate(14, 12, "SKU")], insert_attempts=0)
    table("preview-multiline-cap", "Keep physical line numbers for a capped multiline sample",
          [*records[:8], ("demo-9", "9", "Trail\nMap"), *records[9:]], lines=[*range(2, 11), 12, 13, 14],
          created=[*created[:8], saved("DEMO-9", 9, "Trail\nMap"), *created[9:]])


def atomic_cases():
    note_headers = (*ITEM, "Note")
    for slug, title, note, cleaned, code in (
        ("changed", "A mapped note lets Archive satisfy the model constraint", "Reviewed", "Reviewed", None),
        ("default", "Reject Archive with the default note when both are mapped", "server default", None, "invalid"),
        ("trimmed-default", "Run the Archive check on cleaned note text", " server default ", None, "invalid"),
        ("case-variant", "Compare the Archive note constraint case-sensitively", "Server Default", "Server Default", None),
        ("valid-neighbor", "Allow other labels to keep the mapped default note", "server default", "server default", None),
    ):
        label = "Current" if slug == "valid-neighbor" else "Archive"
        table(f"atomic-note-{slug}", title, [(*ROW, "Reviewed"), ("demo-b", "2", label, note)],
              profile="note", headers=note_headers, valid=[0] if code else None,
              issues=[[3, None, code]] if code else [], insert_attempts=0 if code else 2,
              created=[] if code else [saved(note="Reviewed"), saved("DEMO-B", 2, label, cleaned)])

    for slug, title, records, lines, fail, existing in (
        ("first", "Stop before later inserts when the first insert fails", [("demo-x", "2", "Archive"), ROW],
         [2, 3], 0, []),
        ("middle", "Roll back preceding inserts and stop after a middle failure",
         [ROW, ("demo-x", "2", "Archive"), ("demo-z", "3", "Lamp")], [2, 3, 4], 1, []),
        ("last", "Roll back more than one insert when the last insert fails",
         [ROW, ("demo-b", "2", "Lamp"), ("demo-x", "3", "Archive")], [2, 3, 4], 2, []),
        ("physical-line", "Report the failing insert after a multiline record by start line",
         [("demo-a", "1", "Trail\r\nMap"), ("demo-x", "3", "Archive")], [2, 4], 1, []),
        ("keep-existing", "Preserve existing rows after a late database constraint error",
         [("demo-b", "2", "Map"), ("demo-x", "3", " Archive ")], [2, 3], 1,
         [dict(sku="DEMO-OLD", quantity=1, label="Map", internal_note="Earlier note", active=False)]),
    ):
        table(f"atomic-integrity-{slug}", title, records, lines=lines, existing=existing, insert_attempts=fail + 1,
              apply_issues=[[lines[fail], None, "integrity", "The database rejected the import. No rows were saved."]])

    old = dict(sku="DEMO-A", quantity=1, label="Map", internal_note="Earlier note", active=False)
    for slug, title, cells, line, conflict, issue in (
        ("sku-exact", "Report exact existing SKU as a Django uniqueness error", ("DEMO-A", "2", "Lamp"), 3, "SKU", "unique"),
        ("sku-cleaned", "Check cleaned SKU against existing database rows", (" demo-a ", "2", "Lamp"), 3, "SKU", "unique"),
        ("pair", "Check trimmed label and integer quantity against SQLite", ("demo-c", "01", " Map "), 3, None, "unique_together"),
        ("same-row-both", "Keep field and non-field database uniqueness errors",
         ("DEMO-A", "01", "Map"), 3, None, "both"),
        ("multiline", "Report database conflicts at the start of multiline input",
         ("demo-a", "2", "Trail\nMap"), 3, "SKU", "unique"),
    ):
        errors = [[line, conflict, issue]] if issue != "both" else [[line, None, "unique_together"], [line, "SKU", "unique"]]
        table(f"atomic-existing-{slug}", title, [("demo-b", "4", "Tent"), cells], valid=[0],
              existing=[old], issues=errors, insert_attempts=0)

    for slug, title, records, other, errors in (
        ("new-sku", "Revalidate a formerly free SKU against newly stored rows", [ROW, ("demo-b", "2", "Lamp")],
         [dict(sku="DEMO-B", quantity=7, label="Earlier")], [[3, "SKU", "unique"]]),
        ("new-pair", "Revalidate a formerly free composite key after preview", [ROW, ("demo-b", "02", " Lamp ")],
         [dict(sku="DEMO-OTHER", quantity=2, label="Lamp")], [[3, None, "unique_together"]]),
        ("new-both", "Report two new database conflicts affecting different records", [ROW, ("demo-b", "2", "Lamp")],
         [dict(sku="DEMO-A", quantity=2, label="Lamp")], [[2, "SKU", "unique"], [3, None, "unique_together"]]),
        ("blocked-first", "Do not save later rows when fresh validation fails first", [ROW, ("demo-b", "2", "Lamp")],
         [dict(sku="DEMO-A", quantity=9, label="Earlier")], [[2, "SKU", "unique"]]),
    ):
        table(f"atomic-state-{slug}", title, records, before_apply=other, apply_issues=errors, insert_attempts=0)

    table("atomic-state-unrelated", "Apply after preview when new database state does not conflict",
          [ROW, ("demo-b", "2", "Lamp")], before_apply=[dict(sku="DEMO-Z", quantity=2, label="Map")],
          created=[saved(), saved("DEMO-B", 2, "Lamp")], insert_attempts=2)
    table("atomic-existing-unchanged", "Keep an existing row intact while adding distinct rows",
          [("demo-b", "1", "Lamp"), ("demo-c", "2", "Map")], existing=[old],
          created=[saved("DEMO-B", 1, "Lamp"), saved("DEMO-C", 2, "Map")], insert_attempts=2)

    for slug, title, parent, records, created, error in (
        ("no-parent", "Return a line-less failure when a deferred parent check fails", False,
         [("0",), ("2",)], [], True),
        ("null-no-parent", "Check deferred foreign keys even for a row with a NULL slot", False,
         [("",)], [], True),
        ("parent-found", "Commit both placed rows when the default parent exists", True,
         [("3",), ("",)], [[1001, 3], [1001, None]], False),
    ):
        table(f"atomic-deferred-{slug}", title, records, headers=("Slot",), profile="placement",
              parent=parent, top_level_transaction=True, created=created, insert_attempts=len(records),
              apply_issues=[[None, None, "integrity"]] if error else [])

    table("atomic-product-existing", "Revalidate an existing normalized SKU on the Product model",
          [("demo-p", "1", "0", "Map"), ("demo-b", "2", "2", "Lamp")], profile="product", headers=PRODUCT,
          existing=[dict(sku="DEMO-P", price="3.40", stock=3, name="Existing")], valid=[1],
          issues=[[2, "SKU", "unique"]], insert_attempts=0)
    table("atomic-placement-repeat", "Roll back repeated non-null slots when parent is unmapped",
          [("2",), ("02",)], profile="placement", headers=("Slot",),
          apply_issues=[[3, None, "integrity"]], insert_attempts=2)
    table("atomic-placement-existing", "Preserve existing placements after a later slot conflict",
          [("3",), ("2",)], profile="placement", headers=("Slot",), existing=[dict(item_id=1001, slot=2)],
          apply_issues=[[3, None, "integrity"]], insert_attempts=2)
# fmt: on


def render(case):
    # Keep each expected issue, sample, and database row on one line for review.
    def dump(value):
        return json.dumps(value, ensure_ascii=False)

    fields = [
        f"  {dump(key)}: {dump(value)}"
        for key, value in case.items()
        if key != "expect"
    ]
    expected = []
    for key, value in case["expect"].items():
        if key in {"sample", "issues", "created", "apply_issues"} and value:
            rows = ",\n".join("      " + dump(row) for row in value)
            rendered = "[\n" + rows + "\n    ]"
        else:
            rendered = dump(value)
        expected.append(f"    {dump(key)}: {rendered}")
    fields.append('  "expect": {\n' + ",\n".join(expected) + "\n  }")
    return "{\n" + ",\n".join(fields) + "\n}\n"


def main():
    for build in (
        header_cases,
        text_cases,
        limit_cases,
        item_cases,
        product_cases,
        mapping_cases,
        uniqueness_cases,
        preview_cases,
        atomic_cases,
    ):
        build()
    target = Path(__file__).with_name("regression_vectors")
    target.mkdir(exist_ok=True)
    for slug, case in sorted(CASES.items()):
        (target / f"{slug}.json").write_text(
            render(case), encoding="utf-8", newline="\n"
        )


if __name__ == "__main__":
    main()
