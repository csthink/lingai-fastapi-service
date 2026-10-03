"""Deterministic correction of the known vocabulary source footer."""

import re

SOURCE_FOOTER = '歷年TOPIK 最常出現的必背單字'
# These are source-title markers, not the legitimate word TOPIK itself.
TITLE_MARKERS = re.compile(r'歷年\s*TOPIK|历年\s*TOPIK|最常出現的必背|最常出现的必背|必背單字|必背单字', re.IGNORECASE)


def clean_meaning(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError('Meaning must be a string')
    if value.endswith(SOURCE_FOOTER):
        result = value[:-len(SOURCE_FOOTER)].rstrip()
        if not result:
            raise ValueError('Removing source footer would leave an empty meaning')
        if TITLE_MARKERS.search(result):
            raise ValueError('Repeated or unrecognized source footer')
        return result
    if TITLE_MARKERS.search(value):
        raise ValueError('Unrecognized source footer; manual review required')
    return value
