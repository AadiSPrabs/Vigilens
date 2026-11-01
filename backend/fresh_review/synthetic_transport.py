"""Deterministic OFFLINE synthetic provider transport for developer installs.

Stands in for MetaTransport so a developer (for example the frontend owner) can run the
real governed upload path end to end - real approval check, real ledger reservation, real
journal, real official-parser geometry path - with zero network and zero provider cost.
Replies are deterministic functions of the exact request bytes, are labelled synthetic in
every id and evidence string, and never claim accuracy. This module has no socket, HTTP or
file access. It is not a provider key and does not replace owner source approvals, ledger
authority or a real transport; those stay exactly as gated as in the live runtime.
"""
import base64
import hashlib
import io
import json

from PIL import Image

_PNG_PREFIX = 'data:image/png;base64,'
_PPE_VALUES = ('present', 'absent', 'unknown')


def _check_body(body):
    # Same request rules as MetaTransport: bounded models only, no storage, tools or background.
    if not isinstance(body, dict) or body.get('model') not in ('sam-3.1', 'muse-spark-1.3') or body.get('store') is not False or body.get('tools') or body.get('background'):
        raise ValueError('Only bounded private SAM/PPE requests supported')
    return body['model']


def _body_image(body):
    items = body.get('input')
    if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
        raise ValueError('Single message input required')
    content = items[0].get('content')
    if not isinstance(content, list) or len(content) != 2:
        raise ValueError('Text plus image content required')
    url = content[1].get('image_url') if isinstance(content[1], dict) else None
    if not isinstance(url, str) or not url.startswith(_PNG_PREFIX):
        raise ValueError('PNG data URL image required')
    raw = base64.b64decode(url[len(_PNG_PREFIX):])
    image = Image.open(io.BytesIO(raw))
    image.load()
    if image.format != 'PNG':
        raise ValueError('PNG image required')
    return raw, image


def _person_boxes(width, height, seed):
    """One or two disjoint synthetic person boxes, deterministic from the source bytes."""
    count = 1 + (seed[0] & 1)
    box_h = min(64, height)
    if box_h < 8:
        box_h = height
    y_span = max(1, height - box_h + 1)
    boxes = []
    if count == 2 and width >= 16:
        half = width // 2
        box_w = min(32, half)
        if box_w >= 8:
            x_span_a = max(1, half - box_w + 1)
            x_span_b = max(1, width - half - box_w + 1)
            xa = seed[1] % x_span_a
            xb = half + (seed[2] % x_span_b)
            ya = seed[3] % y_span
            yb = seed[4] % y_span
            boxes = [(xa, ya, xa + box_w - 1, ya + box_h - 1), (xb, yb, xb + box_w - 1, yb + box_h - 1)]
    if not boxes:
        box_w = min(32, width)
        if box_w < 1:
            box_w = width
        x_span = max(1, width - box_w + 1)
        x1 = seed[1] % x_span
        y1 = seed[2] % y_span
        boxes = [(x1, y1, x1 + box_w - 1, y1 + box_h - 1)]
    return boxes


def _sam_segmentation_text(width, height, seed):
    """Official-grammar SAM image text with solid synthetic masks, parseable by the pinned parser."""
    from meta_sam_parser._mask_codec import _encode_raster  # pinned meta-sam-parser==0.0.6; dev-synthetic use only
    parts = []
    for index, (x1, y1, x2, y2) in enumerate(_person_boxes(width, height, seed)):
        box_w, box_h = x2 - x1 + 1, y2 - y1 + 1
        payload = _encode_raster(bytes([1]) * (box_w * box_h), box_w, box_h)
        parts.append('%d<|box;x1=%d;y1=%d;x2=%d;y2=%d;w=%d;h=%d|><|mask;x=0;y=0;data=%d,%d,%s|>'
                     % (index, x1, y1, x2, y2, width, height, box_h, box_w, payload))
    return '<0f>' + ''.join(parts)


def _sse_completed(response):
    return ('data: ' + json.dumps({'type': 'response.completed', 'response': response},
                                  sort_keys=True, separators=(',', ':')) + '\n\n').encode()


class SyntheticTransport:
    """Offline callable with the MetaTransport interface. Never touches the network."""

    def __init__(self, calls=None):
        # Optional caller-supplied list records every request body (test observation only).
        self.calls = calls

    def __call__(self, body):
        model = _check_body(body)
        if self.calls is not None:
            self.calls.append(body)
        raw, image = _body_image(body)
        seed = hashlib.sha256(raw).digest()
        if model == 'sam-3.1':
            text = _sam_segmentation_text(image.width, image.height, seed)
            response = {'model': 'sam-3.1', 'id': 'synthetic-sam-' + seed.hex()[:16], 'status': 'completed',
                        'usage': {'images_processed': 1},
                        'output': [{'type': 'message', 'role': 'assistant', 'status': 'completed',
                                    'content': [{'type': 'output_text', 'text': text}]}]}
            return _sse_completed(response)
        helmet = _PPE_VALUES[seed[5] % 3]
        vest = _PPE_VALUES[seed[6] % 3]
        observed = {'helmet': helmet, 'vest': vest,
                    'helmet_evidence': 'synthetic deterministic value from request bytes; not a real reading',
                    'vest_evidence': 'synthetic deterministic value from request bytes; not a real reading'}
        response = {'id': 'synthetic-ppe-' + seed.hex()[:16], 'status': 'completed', 'model': 'muse-spark-1.3',
                    'usage': {'input_tokens': 64 + len(raw) % 512, 'output_tokens': 48,
                              'input_tokens_details': {'cached_tokens': 0}},
                    'output': [{'type': 'message', 'role': 'assistant', 'status': 'completed',
                                'content': [{'type': 'output_text', 'text': json.dumps(observed, sort_keys=True)}]}]}
        return json.dumps(response, sort_keys=True, separators=(',', ':')).encode()
