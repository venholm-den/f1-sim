"""Optional PDF worker; run with an existing Python containing pdfplumber.

The app environment does not require PDF dependencies or install them at runtime.
"""
import json
import sys

def without_car_number_footnotes(page):
    """Remove only geometrically verified superscript digits beside a car number.

    For example, car 63 plus footnote 1 otherwise becomes car 631 in plain
    text. Keep the original text and the removed boxes as auditable evidence.
    """
    words = page.extract_words(extra_attrs=['size'])
    removed = []
    for base, marker in zip(words, words[1:]):
        if (base['text'].isdigit() and len(base['text'])<=2 and base['x0']<page.width*.15
                and marker['text'].isdigit() and len(marker['text'])<=2
                and 0<=marker['x0']-base['x1']<2
                and marker['size']<base['size']*.8
                and marker['bottom']<base['bottom']-2):
            removed.append({'base':base['text'],'marker':marker['text'],
                            'box':[marker['x0'],marker['top'],marker['x1'],marker['bottom']]})
    def keep(obj):
        if obj.get('object_type')!='char':
            return True
        return not any(obj['x0']>=box[0]-.1 and obj['x1']<=box[2]+.1
                       and obj['top']>=box[1]-.1 and obj['bottom']<=box[3]+.1
                       for box in (item['box'] for item in removed))
    return page.filter(keep).extract_text() or '', removed


def extract(path):
    import pdfplumber
    pages = []
    with pdfplumber.open(path) as document:
        for page in document.pages:
            entry_text, markers = without_car_number_footnotes(page)
            pages.append({'text': page.extract_text() or '',
                          'entry_text': entry_text, 'removed_superscript_markers': markers,
                          'columns': [page.crop(box).extract_text() or '' for box in
                                      [(0, 0, page.width/2, page.height),
                                       (page.width/2, 0, page.width, page.height)]]})
    return {'pages': pages}


if __name__ == '__main__':
    print(json.dumps(extract(sys.argv[1]), ensure_ascii=True))
