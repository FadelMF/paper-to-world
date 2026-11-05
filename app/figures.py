"""Paper figures as images: each captioned figure's page rendered, and the figure cut out of it.

Rendering whole pages also captures vector drawings, which most arXiv diagrams are; embedded
raster images alone would miss them. The cut-out starts as the cluster of drawing objects (paths,
images, shadings) stacked directly above the caption, and is replaced by the box the figure reader
reports when a vision model is configured.
"""

import io
import re

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

SCALE = 2  # 144 dpi: small labels stay legible to a vision model
MARGIN = 0.015  # share of the page kept around a guessed figure
LINE_GAP = 12  # points between text runs that still belong to one caption line
COLUMN_SLACK = 0.1  # a figure may be this share of the page wider than its caption on each side
TOUCH = 0.02  # once a figure has started, drawings must come this close to it sideways to join
GAP = 0.05  # drawing objects further apart than this share of the page height are not one figure
# A form (an embedded drawing, as plots often are) counts as one drawing, unless it wraps a large part of
# the page; then its objects are used, mapped from the form's own space to the page.
GRAPHICS = {pdfium_c.FPDF_PAGEOBJ_PATH, pdfium_c.FPDF_PAGEOBJ_IMAGE, pdfium_c.FPDF_PAGEOBJ_SHADING, pdfium_c.FPDF_PAGEOBJ_FORM}
WHOLE_PAGE = (0.0, 0.0, 1.0, 1.0)
SOLID_POINTS = 4  # a shape narrower or shorter than this is a rule, bar or stroke
SOLID_SHAPES = 3
UNCAPTIONED_AREA = 0.04  # drawings no caption claims become a figure when they cover this share of the page
WRAPPER_AREA = 0.4  # a form covering this share of the page is a container, not a figure
LABEL = re.compile(r"^(?:extended data\s+)?(?:figure|fig\.?)\s*S?\d+", re.I)


def png(image):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def caption_box(textpage, label):
    """PDF-space box (left, bottom, right, top) of the caption's first line, which starts with `label`, or None."""
    searcher = textpage.search(label, match_case=False)
    while (found := searcher.get_next()) is not None:
        index, count = found
        if not re.match(r"\s*[.:|]", textpage.get_text_range(index + count, 2)):
            continue  # an in-text mention such as "Figure 1 shows"
        boxes = [textpage.get_charbox(i) for i in range(index, index + count)]
        left, bottom, right, top = boxes[0][0], min(b[1] for b in boxes), boxes[-1][2], max(b[3] for b in boxes)
        # Extend along the line through text runs that continue it without a column-sized gap.
        middle = (bottom + top) / 2
        for r in sorted((textpage.get_rect(i) for i in range(textpage.count_rects())), key=lambda r: r[0]):
            if r[1] <= middle <= r[3] and r[0] <= right + LINE_GAP and r[2] > right:
                right = r[2]
        return left, bottom, right, top
    return None


def drawings(page, width, height, form=None, matrix=None, level=0):
    """(type, page-space box) of each drawing, descending into forms that wrap a large part of the page."""
    for obj in page.get_objects(max_depth=1, form=form, level=level):
        if obj.type not in GRAPHICS:
            continue
        box = obj.get_bounds() if matrix is None else matrix.on_rect(*obj.get_bounds())
        if obj.type == pdfium_c.FPDF_PAGEOBJ_FORM and (box[2] - box[0]) * (box[3] - box[1]) > WRAPPER_AREA * width * height and level < 4:
            inner = obj.get_matrix() if matrix is None else obj.get_matrix().multiply(matrix)
            yield from drawings(page, width, height, obj, inner, level + 1)
        else:
            yield obj.type, box


def drawing_boxes(page, width, height):
    return (box for _, box in drawings(page, width, height))


def guess_box(page, width, height, caption):
    """Fractional (x0, y0, x1, y1), top-left origin: drawings stacked directly above the caption.

    The region grows from the caption upward, taking drawings that start within GAP of it: the first within
    COLUMN_SLACK of the caption's sides, the rest within TOUCH of the region, so a neighbouring column stays out."""
    top = caption[3]
    # Drawings mostly above the caption, cut at its top: a form's box often runs on through the caption's whitespace.
    # Page-wide rules and backgrounds are left out.
    candidates = [
        (b[0], max(b[1], top), b[2], b[3])
        for b in drawing_boxes(page, width, height)
        if b[3] - max(b[1], top) >= 0.5 * (b[3] - b[1]) > 0 and b[2] - b[0] <= 0.98 * width and b[3] - b[1] <= 0.9 * height
    ]
    left, right, reach, region = caption[0], caption[2], top, None
    grew = True
    while grew:
        grew = False
        for box in list(candidates):
            slack = (COLUMN_SLACK if region is None else TOUCH) * width
            if box[1] - reach <= GAP * height and box[2] >= left - slack and box[0] <= right + slack:
                region = box if region is None else (min(region[0], box[0]), min(region[1], box[1]), max(region[2], box[2]), max(region[3], box[3]))
                left, right, reach = min(caption[0], region[0]), max(caption[2], region[2]), max(reach, box[3])
                candidates.remove(box)
                grew = True
    if region is None:
        return WHOLE_PAGE
    x0, bottom, x1, upper = region
    return (max(0.0, x0 / width - MARGIN), max(0.0, 1 - upper / height - MARGIN), min(1.0, x1 / width + MARGIN), min(1.0, 1 - bottom / height + MARGIN))


def crop(page_image, box):
    width, height = page_image.size
    x0, y0, x1, y1 = box
    return page_image.crop((round(x0 * width), round(y0 * height), round(x1 * width), round(y1 * height)))


def drawing_clusters(page, width, height):
    """Groups of drawings that touch or sit within GAP of each other: (page-space box, has a picture).

    A group is a picture when it holds a raster image or a form, or at least SOLID_SHAPES shapes that have
    both width and height; equations, tables and algorithm boxes are mostly thin rules and bars."""
    clusters = []  # [box, pictures, solid shapes]
    for kind, box in sorted(drawings(page, width, height), key=lambda d: d[1][1]):
        if box[2] - box[0] > 0.98 * width or box[3] - box[1] > 0.9 * height:
            continue  # page-wide rules, backgrounds and the image of a scanned page
        reach = GAP * height
        merged = [box, kind != pdfium_c.FPDF_PAGEOBJ_PATH, min(box[2] - box[0], box[3] - box[1]) > SOLID_POINTS]
        for c in [c for c in clusters if box[0] <= c[0][2] + reach and box[2] >= c[0][0] - reach and box[1] <= c[0][3] + reach and box[3] >= c[0][1] - reach]:
            merged = [
                (min(merged[0][0], c[0][0]), min(merged[0][1], c[0][1]), max(merged[0][2], c[0][2]), max(merged[0][3], c[0][3])),
                merged[1] + c[1],
                merged[2] + c[2],
            ]
            clusters.remove(c)
        clusters.append(merged)
    return [(box, pictures > 0 or solid >= SOLID_SHAPES) for box, pictures, solid in clusters]


def covered(box, others):
    """Whether most of fractional `box` lies inside one of `others`."""
    area = (box[2] - box[0]) * (box[3] - box[1])
    for o in others:
        inner = max(0, min(box[2], o[2]) - max(box[0], o[0])) * max(0, min(box[3], o[3]) - max(box[1], o[1]))
        if inner > 0.5 * area:
            return True
    return False


def render_figures(pdf_bytes, captions):
    """Every figure with its rendered page image and box: one per caption, then drawings that no caption
    claims (at least UNCAPTIONED_AREA of the page), with ids like figP3a and an empty caption."""
    document = pdfium.PdfDocument(pdf_bytes)
    figures = []
    try:
        for number in range(1, len(document) + 1):
            page = document[number - 1]
            width, height = page.get_size()
            image = None
            boxes = []
            for caption in (c for c in captions if c["page"] == number):
                label = LABEL.match(caption["caption"])
                found = caption_box(page.get_textpage(), label.group(0)) if label else None
                box = [round(v, 4) for v in (guess_box(page, width, height, found) if found else WHOLE_PAGE)]
                image = image or page.render(scale=SCALE).to_pil()
                figures.append({**caption, "box": box, "page_image": image})
                boxes.append(box)
            letters = iter("abcdefghijklmnopqrstuvwxyz")
            for (left, bottom, right, top), picture in drawing_clusters(page, width, height):
                if not picture:
                    continue
                box = [
                    round(max(0.0, left / width - MARGIN), 4),
                    round(max(0.0, 1 - top / height - MARGIN), 4),
                    round(min(1.0, right / width + MARGIN), 4),
                    round(min(1.0, 1 - bottom / height + MARGIN), 4),
                ]
                if (box[2] - box[0]) * (box[3] - box[1]) < UNCAPTIONED_AREA or covered(box, boxes):
                    continue
                image = image or page.render(scale=SCALE).to_pil()
                figures.append({"id": f"figP{number}{next(letters)}", "page": number, "caption": "", "box": box, "page_image": image})
                boxes.append(box)
    finally:
        document.close()
    return figures


def page_images(pdf_bytes, numbers):
    """PNG renders of the given 1-based page numbers."""
    document = pdfium.PdfDocument(pdf_bytes)
    try:
        return {n: png(document[n - 1].render(scale=SCALE).to_pil()) for n in numbers if 1 <= n <= len(document)}
    finally:
        document.close()


def page_count(pdf_bytes):
    document = pdfium.PdfDocument(pdf_bytes)
    try:
        return len(document)
    finally:
        document.close()


def save_figure(run_dir, figure, box):
    """Write the cut-out as figure-<n>.png next to the run's other artifacts; return its name."""
    name = f"figure-{figure['id'].removeprefix('fig')}.png"  # figure-1.png, figure-S1.png, figure-P3a.png
    (run_dir / name).write_bytes(png(crop(figure["page_image"], box)))
    return name
