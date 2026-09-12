#!/usr/bin/env python3
"""
rawfetch.py: exact page text for verbatim quotes, no LLM.

Fetches a URL and prints its JSON-LD structured data and/or its visible text, verbatim
(entities unescaped, tags stripped, no paraphrasing). Exists because an AI-summarising
fetch tool gave two materially different paraphrases of the same job posting -- quotes
for an episode must come from the page's actual text.

  rawfetch.py URL [--grep PHRASE]... [--mode auto|jsonld|text] [--context 300] [--out FILE]
  rawfetch.py --selftest

  rawfetch.py 'https://example.com/job/123' --grep 'a hands-on role'
      -> FOUND "a hands-on role" [visible]: ...the enclosing block (<=~300 chars)...
         exits 1 if any --grep phrase is not found (so it doubles as a verifier)
         exits 2 on a fetch/input error (bad URL, non-HTML content, empty phrase, ...)

  rawfetch.py 'https://example.com/job/123' --mode jsonld
      -> just the JobPosting/Article JSON-LD, decoded to plain text

--grep only ever searches (a) visible-text blocks and (b) the text-bearing JSON-LD string
fields (JobPosting title/description, Article/NewsArticle/BlogPosting headline/articleBody/
description) -- never this script's own formatted labels or a raw JSON dump. A match must
lie inside one block (no crossing a heading/list-item/paragraph boundary) and have a
non-alphanumeric character (or block edge) on both sides, so "5+ years" can't satisfy a
search for "years" cut out of "15+ years".
"""
import argparse, gzip, html.parser, http.client, json, re, sys
import urllib.error, urllib.request

UA = ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/124.0.0.0 Safari/537.36')
READ_CAP = 5 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {'text/html', 'application/xhtml+xml', 'text/plain'}
JSONLD_RE = re.compile(
    r'<script\b(?=[^>]*\btype=["\']application/ld\+json["\'])[^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL)
ARTICLE_TYPES = {'Article', 'NewsArticle', 'BlogPosting'}


class FetchError(Exception):
    pass


def _check_content_type(ctype_header):
    """Raises FetchError for a declared-and-disallowed content type. A missing/empty
    header is permissive (some minimal servers omit it)."""
    ctype = (ctype_header or '').split(';')[0].strip().lower()
    if ctype and ctype not in ALLOWED_CONTENT_TYPES:
        raise FetchError(f'unsupported content type "{ctype}" (want text/html-like)')


def sniff_meta_charset(raw):
    head = raw[:4096].decode('ascii', errors='ignore')
    m = re.search(r'<meta[^>]+charset=["\']?\s*([A-Za-z0-9_-]+)', head, re.IGNORECASE)
    return m.group(1) if m else None


def _decode(raw, header_charset):
    candidates = [header_charset] if header_charset else [sniff_meta_charset(raw)]
    candidates.append('utf-8')
    for enc in candidates:
        if not enc:
            continue
        try:
            return raw.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode('utf-8', errors='replace')


def fetch(url):
    """Returns (decoded_text, final_url). Raises FetchError for anything that stops us
    getting clean page text -- HTTP errors, DNS/timeout/connection failures, a non-HTML
    content type, or a broken/truncated response."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Encoding': 'gzip'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            final_url = resp.geturl()
            _check_content_type(resp.headers.get('Content-Type'))
            raw = resp.read(READ_CAP + 1)
            if len(raw) > READ_CAP:
                raw = raw[:READ_CAP]
                print(f'warning: response truncated to {READ_CAP} bytes (5 MB cap)', file=sys.stderr)
            if 'gzip' in (resp.headers.get('Content-Encoding') or '').lower():
                raw = gzip.decompress(raw)
            charset = resp.headers.get_content_charset()
    except FetchError:
        raise
    except urllib.error.HTTPError as e:
        raise FetchError(f'HTTP error {e.code} fetching {url}: {e.reason}')
    except urllib.error.URLError as e:
        raise FetchError(f'error fetching {url}: {e.reason}')
    except (TimeoutError, OSError, EOFError, ValueError, UnicodeError, http.client.IncompleteRead) as e:
        raise FetchError(f'error fetching {url}: {e}')

    if final_url != url:
        print(f'note: redirected to {final_url}', file=sys.stderr)
    return _decode(raw, charset), final_url


BLOCK_SEP = '\x00'

# Elements HTML lets an author leave unclosed, and the well-defined trigger that implicitly
# closes them anyway (a sibling opening, or a specific ancestor opening/closing) -- so a
# never-closed hidden <p>/<li>/<td>/... doesn't hide everything for the rest of the page.
IMPLICIT_CLOSE_ON_SIBLING_OPEN = {
    'li': {'li'}, 'dt': {'dt', 'dd'}, 'dd': {'dt', 'dd'},
    'td': {'td', 'th', 'tr'}, 'th': {'td', 'th', 'tr'}, 'tr': {'tr'}, 'option': {'option'},
}
IMPLICIT_CLOSE_ON_PARENT = {
    'li': {'ul', 'ol'}, 'dt': {'dl'}, 'dd': {'dl'},
    'td': {'tr', 'table', 'tbody', 'thead', 'tfoot'}, 'th': {'tr', 'table', 'tbody', 'thead', 'tfoot'},
    'tr': {'table', 'tbody', 'thead', 'tfoot'}, 'option': {'select'},
}
# <nav> has no such spec rule, but a never-closed one otherwise leaks its "every <a> is a
# separate item" scoping onto the rest of the page -- close it when a real sectioning
# boundary is crossed instead.
NAV_IMPLICIT_CLOSERS = {'main', 'article', 'section', 'footer', 'body'}


class TextExtractor(html.parser.HTMLParser):
    """Visible-text extraction: skips script/style/etc and hidden subtrees, breaks lines
    at block-level elements, tolerates an unclosed <head> (forced shut when <body> starts),
    never lets a void element (no content, no end tag) hide anything past itself, keeps a
    hidden ancestor hidden through a mismatched end tag rather than un-hiding early, and
    implicitly closes the standard "optional end tag" elements (p, li, dt/dd, td/th, tr,
    option) and a dangling <nav> so an unclosed one doesn't swallow the rest of the page."""
    SKIP = {'script', 'style', 'noscript', 'svg', 'template', 'head'}
    # Full HTML block-level set (td/th included deliberately -- table cells must not join
    # into one searchable block, e.g. "Remote"+"No" must never read as "Remote No").
    BLOCK = {'address', 'article', 'aside', 'blockquote', 'dd', 'details', 'dialog', 'div',
             'dl', 'dt', 'fieldset', 'figcaption', 'figure', 'footer', 'form',
             'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'header', 'hgroup', 'hr', 'li', 'main',
             'nav', 'ol', 'p', 'pre', 'section', 'summary', 'table', 'tbody', 'thead',
             'tfoot', 'tr', 'td', 'th', 'ul', 'br', 'menu'}
    # Void elements have no content and no closing tag -- never push a stack frame for one
    # (a stray aria-hidden/hidden attribute on <img>/<input> must not hide its siblings).
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta',
            'source', 'track', 'wbr'}
    # The real HTML rule for what implicitly closes a <p> -- deliberately NOT the same as
    # BLOCK. <br> is a block-level line separator for grep purposes but browsers do NOT close
    # a <p> when a <br> starts inside it (a hidden <p> must stay hidden through a <br>); <hr>
    # DOES close a <p>, so it stays in this narrower set.
    P_CLOSING_TAGS = {'address', 'article', 'aside', 'blockquote', 'details', 'div', 'dl',
                       'fieldset', 'figcaption', 'figure', 'footer', 'form',
                       'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'header', 'hgroup', 'hr', 'main',
                       'menu', 'nav', 'ol', 'p', 'pre', 'section', 'table', 'ul'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.skip_depth = 0
        self.hidden_depth = 0
        self.pre_depth = 0
        self.nav_depth = 0
        self.parts = []

    @staticmethod
    def _is_hidden(attrs_dict):
        if 'hidden' in attrs_dict:
            return True
        if (attrs_dict.get('aria-hidden') or '').strip().lower() == 'true':
            return True
        style = re.sub(r'\s+', '', (attrs_dict.get('style') or '').lower())
        return 'display:none' in style

    def _push(self, tag, attrs):
        attrs_dict = dict(attrs)
        is_skip, is_hidden = tag in self.SKIP, self._is_hidden(attrs_dict)
        is_pre, is_nav = tag == 'pre', tag == 'nav'
        self.stack.append({'tag': tag, 'skip': is_skip, 'hidden': is_hidden, 'pre': is_pre, 'nav': is_nav})
        self.skip_depth += is_skip
        self.hidden_depth += is_hidden
        self.pre_depth += is_pre
        self.nav_depth += is_nav

    def _close_matching(self, tag):
        """Closes only the OWN most-recently-opened frame for `tag`. Deliberately does NOT
        cascade-close whatever sits above it: '<p>Intro<div hidden>x</p>secret</div>' is
        malformed (the div is still open when </p> arrives), and 'secret' must stay hidden
        rather than being revealed by the mismatched </p>."""
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i]['tag'] == tag:
                frame = self.stack.pop(i)
                if frame['skip']:
                    self.skip_depth = max(0, self.skip_depth - 1)
                if frame['hidden']:
                    self.hidden_depth = max(0, self.hidden_depth - 1)
                if frame['pre']:
                    self.pre_depth = max(0, self.pre_depth - 1)
                if frame['nav']:
                    self.nav_depth = max(0, self.nav_depth - 1)
                return

    def _force_close_all(self, tag):
        """Closes `tag` AND everything opened after it -- used only to force an unclosed
        <head> shut the moment <body> begins."""
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i]['tag'] == tag:
                for frame in self.stack[i:]:
                    if frame['skip']:
                        self.skip_depth = max(0, self.skip_depth - 1)
                    if frame['hidden']:
                        self.hidden_depth = max(0, self.hidden_depth - 1)
                    if frame['pre']:
                        self.pre_depth = max(0, self.pre_depth - 1)
                    if frame['nav']:
                        self.nav_depth = max(0, self.nav_depth - 1)
                del self.stack[i:]
                return

    def _is_open(self, tag):
        return any(f['tag'] == tag for f in self.stack)

    def _is_nav_link(self, tag):
        # Inside <nav>, treat each <a> as its own item (like <li>) -- two adjacent nav
        # links joined by nothing but a whitespace text node are separate destinations,
        # not one continuous sentence, unlike an <a> inline within a shared <p>.
        return tag == 'a' and self.nav_depth > 0

    def _implicit_close_for_start(self, new_tag):
        if new_tag in NAV_IMPLICIT_CLOSERS and self._is_open('nav'):
            self._force_close_all('nav')
        while self.stack:
            top = self.stack[-1]['tag']
            if top == 'p' and new_tag in self.P_CLOSING_TAGS:
                self._close_matching('p'); continue
            if new_tag in IMPLICIT_CLOSE_ON_SIBLING_OPEN.get(top, ()):
                self._close_matching(top); continue
            break

    def _implicit_close_for_end(self, tag):
        if tag in NAV_IMPLICIT_CLOSERS and self._is_open('nav'):
            self._force_close_all('nav')
        while self.stack:
            top = self.stack[-1]['tag']
            if top == 'p' and tag != 'p' and self._is_open(tag):
                self._close_matching('p'); continue
            if tag in IMPLICIT_CLOSE_ON_PARENT.get(top, ()):
                self._close_matching(top); continue
            break

    def handle_starttag(self, tag, attrs):
        if tag == 'body':
            self._force_close_all('head')
        self._implicit_close_for_start(tag)
        if tag in self.BLOCK or self._is_nav_link(tag):
            self.parts.append(BLOCK_SEP)
        if tag not in self.VOID:
            self._push(tag, attrs)

    def handle_startendtag(self, tag, attrs):
        if tag in self.BLOCK:
            self.parts.append(BLOCK_SEP)
        # self-closing syntax never opens a frame, void or not -- no content to wrap.

    def handle_endtag(self, tag):
        is_nav_link = self._is_nav_link(tag)
        self._implicit_close_for_end(tag)
        self._close_matching(tag)
        if tag in self.BLOCK or is_nav_link:
            self.parts.append(BLOCK_SEP)

    def handle_data(self, data):
        if self.skip_depth == 0 and self.hidden_depth == 0:
            if self.pre_depth > 0 and '\n' in data:
                data = data.replace('\n', BLOCK_SEP)
            self.parts.append(data)

    def text(self):
        blocks = (re.sub(r'\s+', ' ', b).strip() for b in ''.join(self.parts).split(BLOCK_SEP))
        return '\n'.join(b for b in blocks if b)


def html_to_text(fragment):
    """Single-pass HTML-to-text, used for the whole page's visible text. Deliberately never
    re-parses its own output -- a legitimately escaped '<tag>'-looking substring in real
    content (e.g. 'std::vector&lt;int&gt;', decoded to literal 'std::vector<int>' text) must
    survive as-is, not be mistaken for markup and stripped on a second pass."""
    p = TextExtractor()
    p.feed(fragment or '')
    return p.text()


_TAG_RE = re.compile(r'<(/?)([a-zA-Z][a-zA-Z0-9]*)\b[^>]*?/?>')
# Recognized inline elements for the "matched open/close pair" test below. Block-level tags
# (TextExtractor.BLOCK, which includes 'br') are handled separately and count on their own,
# open OR close, unpaired -- a bare mention of one real block tag (or a bare <br>/<br/>) is
# already strong evidence of real markup.
_KNOWN_INLINE_TAGS = {'a', 'b', 'i', 'em', 'strong', 'span', 'code', 'u', 'small', 'mark',
                       'sub', 'sup', 'abbr', 'cite', 'q', 'kbd', 'samp', 'var', 'time'}


def _looks_like_html(text):
    """True only if `text` contains a block-level tag (open or close -- BLOCK includes 'br',
    so a bare <br>/<br/> counts on its own), or at least one genuinely MATCHED open/close
    pair of a known inline element (e.g. '<b>...</b>'). A bare, unmatched '<b>' or '<strong>'
    mentioned in plain prose ('Know <b> vs <strong>') must NOT count -- that is not markup,
    just text that happens to mention tag names."""
    opened, closed = set(), set()
    for m in _TAG_RE.finditer(text):
        is_close, name = bool(m.group(1)), m.group(2).lower()
        if name in TextExtractor.BLOCK:
            return True
        if name in _KNOWN_INLINE_TAGS:
            (closed if is_close else opened).add(name)
    return bool(opened & closed)


# The narrower set that makes '\n' insignificant whitespace once parsed as HTML. Deliberately
# NOT the same as TextExtractor.BLOCK/_looks_like_html's tag recognition: inline tags (b,
# strong, a, span, ...) and a bare <br> are real markup worth stripping, but they must NOT
# switch a value into "newline is just whitespace" mode -- only an actual block-level tag,
# which already creates its own real block boundary, does that.
_NEWLINE_INSIGNIFICANT_TAGS = {'p', 'div', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                                'table', 'tr', 'td', 'th', 'blockquote', 'pre', 'section',
                                'article', 'dl', 'dt', 'dd'}


def _has_block_tag(text):
    return any(m.group(2).lower() in _NEWLINE_INSIGNIFICANT_TAGS for m in _TAG_RE.finditer(text))


def jsonld_field_to_blocks(value):
    """Turns a JSON-LD text field into grep-corpus blocks (one per line).
    - If the raw value looks like real HTML (see _looks_like_html), parse it as HTML.
      A blank line ('\\n\\s*\\n') is always a break. Beyond that: if it contains a real
      block-level tag (_has_block_tag), a lone embedded '\\n' is just source-formatting
      whitespace, collapsed like any other whitespace run (that tag already makes its own
      block boundary). If the markup is inline-only (b/strong/a/span/... or a bare <br>,
      with no block tag at all), every '\\n' IS still a meaningful line break -- inline tags
      must not switch a value into whitespace mode -- so it's folded in before parsing.
      Never re-parsed either way.
    - If it doesn't look like HTML, but *unescaping* it reveals real HTML (true double
      HTML-entity encoding, e.g. '&amp;lt;p&amp;gt;...'), parse the unescaped form as HTML
      instead, under the same rules above -- this checks the INPUT's shape, never the parsed
      output, so a genuinely escaped '<tag>'-looking phrase inside otherwise real markup is
      never mistaken for it.
    - Otherwise it's genuinely plain text -- even if it bare-mentions a tag name like '<b>'
      -- so it is NEVER run through the tag parser (which would wrongly consume a literal
      '<b>' as if it opened an element): split on '\\n'/'\\r\\n', a meaningful paragraph/item
      break, and keep every character, tag-like or not, exactly as written."""
    text = str(value)
    if _looks_like_html(text):
        source = text
    else:
        unescaped = html.unescape(text)
        source = unescaped if _looks_like_html(unescaped) else None

    if source is not None:
        source = re.sub(r'\r\n|\r', '\n', source)
        source = re.sub(r'\n[ \t]*\n[ \t\n]*', BLOCK_SEP, source)  # a blank line is always a break
        if not _has_block_tag(source):
            source = source.replace('\n', BLOCK_SEP)
        rendered = html_to_text(source)
    else:
        normalized = re.sub(r'\r\n|\r', '\n', html.unescape(text))
        rendered = '\n'.join(re.sub(r'[ \t]+', ' ', ln).strip() for ln in normalized.split('\n'))
    return [ln.strip() for ln in rendered.split('\n') if ln.strip()]


def extract_jsonld_blocks(html_text):
    return [m.group(1).strip() for m in JSONLD_RE.finditer(html_text)]


def flatten_jsonld(obj):
    if isinstance(obj, list):
        return [item for o in obj for item in flatten_jsonld(o)]
    if isinstance(obj, dict):
        if isinstance(obj.get('@graph'), list):
            return [item for o in obj['@graph'] for item in flatten_jsonld(o)]
        return [obj]
    return []


def parse_jsonld_blocks(html_text):
    """Returns (items, notes) -- notes are stderr-worthy strings for malformed blocks."""
    items, notes = [], []
    for raw in extract_jsonld_blocks(html_text):
        try:
            items.extend(flatten_jsonld(json.loads(raw)))
        except json.JSONDecodeError as e:
            notes.append(f'skipping malformed JSON-LD block: {e}')
    return items, notes


def item_types(item):
    t = item.get('@type')
    if isinstance(t, list):
        return t
    if isinstance(t, str):
        return [t]
    return []


def _name_of(value):
    if isinstance(value, dict):
        return value.get('name', '')
    if isinstance(value, list):
        return ', '.join(_name_of(v) for v in value if _name_of(v))
    if isinstance(value, str):
        return value
    return ''


def format_salary(sal):
    if not isinstance(sal, dict):
        return str(sal)
    currency = sal.get('currency', '')
    value = sal.get('value')
    if isinstance(value, dict):
        unit = value.get('unitText', '')
        lo, hi = value.get('minValue'), value.get('maxValue')
        if lo is not None and hi is not None:
            return f'{currency} {lo}-{hi}/{unit}'.strip()
        v = value.get('value')
        if v is not None:
            return f'{currency} {v}/{unit}'.strip()
    return json.dumps(sal)[:200]


def format_job_posting(item):
    org = item.get('hiringOrganization')
    loc = item.get('jobLocation')
    loc = loc[0] if isinstance(loc, list) and loc else loc
    addr = loc.get('address', {}) if isinstance(loc, dict) else {}
    addr = addr if isinstance(addr, dict) else {}
    city, region = addr.get('addressLocality', ''), addr.get('addressRegion', '')
    lines = [
        f'Title: {item.get("title", "")}',
        f'Posted: {item.get("datePosted", "")}',
        f'Organization: {_name_of(org)}',
        f'Location: {", ".join(x for x in (city, region) if x)}',
    ]
    if item.get('baseSalary'):
        lines.append(f'Salary: {format_salary(item["baseSalary"])}')
    lines += ['', html_to_text(item.get('description', ''))]
    return '\n'.join(lines)


def format_article(item):
    lines = [
        f'Headline: {item.get("headline", "")}',
        f'Published: {item.get("datePublished", "")}',
        f'Author: {_name_of(item.get("author"))}',
        '',
        html_to_text(item.get('articleBody', '')) or item.get('articleBody', ''),
    ]
    return '\n'.join(lines)


def format_other(item):
    types = item_types(item)
    dump = json.dumps(item, separators=(',', ':'))[:2000]
    return f'Type: {", ".join(types) or "Unknown"}\n{dump}'


def render_jsonld(html_text):
    """Human-readable display for --mode jsonld/auto. NOT used for --grep (see the
    jsonld_grep_blocks/build_grep_corpus family below, which is deliberately narrower)."""
    items, notes = parse_jsonld_blocks(html_text)
    for note in notes:
        print(note, file=sys.stderr)
    sections = []
    for item in items:
        types = set(item_types(item))
        if 'JobPosting' in types:
            sections.append(format_job_posting(item))
        elif types & ARTICLE_TYPES:
            sections.append(format_article(item))
        else:
            sections.append(format_other(item))
    return '\n\n'.join(sections)


def render_text(html_text):
    return html_to_text(html_text)


# ---- grep corpus: visible blocks + specific JSON-LD text fields only, never labels/dumps ----

def visible_grep_blocks(html_text):
    return [('visible', ln) for ln in html_to_text(html_text).split('\n') if ln.strip()]


def jsonld_grep_blocks(html_text):
    items, _ = parse_jsonld_blocks(html_text)
    blocks = []
    for item in items:
        types = set(item_types(item))
        if 'JobPosting' in types:
            if item.get('title'):
                blocks += [('jsonld:JobPosting.title', ln) for ln in jsonld_field_to_blocks(item['title'])]
            if item.get('description'):
                blocks += [('jsonld:JobPosting.description', ln)
                           for ln in jsonld_field_to_blocks(item['description'])]
        matched = types & ARTICLE_TYPES
        if matched:
            tname = sorted(matched)[0]
            if item.get('headline'):
                blocks += [(f'jsonld:{tname}.headline', ln) for ln in jsonld_field_to_blocks(item['headline'])]
            for field in ('articleBody', 'description'):
                if item.get(field):
                    blocks += [(f'jsonld:{tname}.{field}', ln)
                               for ln in jsonld_field_to_blocks(item[field])]
    return blocks


def build_grep_corpus(html_text, mode):
    corpus = []
    if mode in ('auto', 'jsonld'):
        corpus += jsonld_grep_blocks(html_text)
    if mode in ('auto', 'text'):
        corpus += visible_grep_blocks(html_text)
    return corpus


QUOTE_MAP = str.maketrans({'‘': "'", '’': "'", '“': '"', '”': '"', '–': '-', '—': '-'})


def normalize(s):
    return re.sub(r'\s+', ' ', s.translate(QUOTE_MAP)).strip()


def _digit_run_len_at(haystack, pos):
    """Length of the maximal run of consecutive digits starting at `pos` (0 if none)."""
    n = 0
    while pos + n < len(haystack) and haystack[pos + n].isdigit():
        n += 1
    return n


def _digit_run_len_before(haystack, pos):
    """Length of the maximal run of consecutive digits ending just before `pos` (0 if none)."""
    n = 0
    i = pos - 1
    while i >= 0 and haystack[i].isdigit():
        n += 1
        i -= 1
    return n


def _is_grouping_comma(haystack, comma_pos):
    """True if the comma at `comma_pos` looks like a real digit-grouping separator: a 1-3
    digit group immediately before it and a 2-3 digit group immediately after. 2-3 (not just
    3) covers Indian-style grouping ("12,34,567"), where every group but the last is 2
    digits, as well as the Western 3-digit convention ("1,300,000"). This necessarily also
    accepts some ordinary comma-separated lists ("sizes 20,30,40") as if they were one grouped
    number -- there is no way to tell the two apart from digits alone, and a false NOT FOUND
    on a real number is judged safer than a false FOUND stitching two list items together."""
    after = _digit_run_len_at(haystack, comma_pos + 1)
    before = _digit_run_len_before(haystack, comma_pos)
    return after in (2, 3) and 1 <= before <= 3


def _bounded_find(haystack, needle):
    """All start indices of needle where both edges are real word/number boundaries:
    - the adjacent char (if any) must not be alphanumeric (str.isalnum(), unicode-aware,
      so 'caf' can't match inside 'café'), AND
    - if the adjacent char is '.' and the char beyond it is a digit and the phrase's own
      edge char on that side is a digit, the boundary is invalid -- so '5 years' can't
      match inside '2.5 years' (a decimal point, unlike a comma, is never itself part of a
      grouped-digits pattern, so any adjoining digit disqualifies it), AND
    - if the adjacent char is ',' and it looks like a real digit-grouping separator (see
      _is_grouping_comma) and the phrase's own edge char on that side is a digit, the
      boundary is invalid -- so '300,000' can't match inside '$1,300,000', and '34,567 INR'
      can't match inside '12,34,567 INR' (Indian grouping).
    haystack/needle are assumed already lowercased (case-insensitive search)."""
    idxs, start = [], 0
    n = len(needle)
    first_is_digit, last_is_digit = needle[0].isdigit(), needle[-1].isdigit()
    while True:
        idx = haystack.find(needle, start)
        if idx == -1:
            return idxs
        end = idx + n
        before_ok = True
        if idx > 0:
            ch = haystack[idx - 1]
            if ch.isalnum():
                before_ok = False
            elif ch == '.' and idx - 2 >= 0 and haystack[idx - 2].isdigit() and first_is_digit:
                before_ok = False
            elif ch == ',' and first_is_digit and _is_grouping_comma(haystack, idx - 1):
                before_ok = False
        after_ok = True
        if end < len(haystack):
            ch = haystack[end]
            if ch.isalnum():
                after_ok = False
            elif ch == '.' and end + 1 < len(haystack) and haystack[end + 1].isdigit() and last_is_digit:
                after_ok = False
            elif ch == ',' and last_is_digit and _is_grouping_comma(haystack, end):
                after_ok = False
        if before_ok and after_ok:
            idxs.append(idx)
        start = idx + 1


def block_snippet(block, idx, needle_len, max_chars):
    """The enclosing block, truncated to ~max_chars centered on the match."""
    if len(block) <= max_chars:
        return block
    center = idx + needle_len // 2
    half = max_chars // 2
    start = max(0, center - half)
    end = min(len(block), start + max_chars)
    start = max(0, end - max_chars)
    return ('…' if start > 0 else '') + block[start:end] + ('…' if end < len(block) else '')


def compute_grep_results(corpus, phrases, max_chars):
    norm_corpus = [(label, normalize(block)) for label, block in corpus]
    results = []
    for phrase in phrases:
        needle = normalize(phrase).lower()
        hit = None
        for label, block in norm_corpus:
            idxs = _bounded_find(block.lower(), needle)
            if idxs:
                hit = (label, block_snippet(block, idxs[0], len(needle), max_chars))
                break
        if hit:
            results.append({'phrase': phrase, 'found': True, 'label': hit[0], 'context': hit[1]})
        else:
            results.append({'phrase': phrase, 'found': False, 'label': None, 'context': None})
    return results


def validate_phrases(phrases):
    """Raises ValueError for an empty or whitespace-only --grep phrase (MED: it must not
    silently count as a match)."""
    for p in phrases:
        if not p or not p.strip():
            raise ValueError(f'empty or whitespace-only --grep phrase is not allowed: {p!r}')


def grep_exit_code(results):
    return 0 if all(r['found'] for r in results) else 1


def format_grep_results(results):
    lines = []
    for r in results:
        if r['found']:
            lines.append(f'FOUND "{r["phrase"]}" [{r["label"]}]: {r["context"]}')
        else:
            lines.append(f'NOT FOUND "{r["phrase"]}"')
    return '\n'.join(lines)


FIXTURE_HTML = '''<!DOCTYPE html>
<html><head><title>Job</title>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"JobPosting","title":"Director of Engineering",
"datePosted":"2026-08-01","hiringOrganization":{"@type":"Organization","name":"Acme Corp"},
"jobLocation":{"@type":"Place","address":{"addressLocality":"Seattle","addressRegion":"WA"}},
"baseSalary":{"@type":"MonetaryAmount","currency":"USD","value":{"@type":"QuantitativeValue",
"minValue":180000,"maxValue":220000,"unitText":"YEAR"}},
"description":"<p>This is a hands-on role &amp; it goes from a flaky test in CI to a platform \
thesis. It&#8217;s exciting.</p>"}
</script>
<script type="application/ld+json">
{ this is not valid json, oops
</script>
<script type="application/ld+json">
{"@type":"Organization","name":"Acme","description":"internal blurb never shown"}
</script>
</head>
<body>
<div>
<p>Visible paragraph with a ‘curly’ quote and a “double” quote and an em \
dash — here.</p>
<ul><li>Lead a team</li><li>of 40 engineers across 3 time zones</li></ul>
<h2>Requirements</h2><p>15+ years of experience required. Not a remote role.</p>
<div style="display:none" hidden aria-hidden="true">Similar job: requires 10 years management</div>
<script>var noise = "should not appear in visible text, e.g. a hands-on role";</script>
<p>Second paragraph line.</p>
</div>
</body></html>'''

NOHEAD_HTML = '<html><head><title>t</title><meta charset="utf-8"><body><p>visible body phrase</p></body></html>'
CP1252_META_HTML = '<html><head><meta charset="windows-1252"></head><body><p>role</p></body></html>'.encode('ascii')

# HIGH-1 residual: crossing through block-level tags beyond the original p/div/li/h*/tr set,
# void elements that must not hide siblings, and a mismatched-nesting hidden frame.
BLOCKS_HTML = '''<html><body>
<dl><dt>Term</dt><dd>Lead a team</dd><dd>of 40 engineers</dd></dl>
<blockquote>Quoted intro</blockquote><p>Quote follow-up</p>
<header>Header text</header><main>Main text</main>
<nav>Nav text</nav><p>After nav</p>
<figcaption>Caption text</figcaption><footer>Footer text</footer>
<pre>Pre line one
Pre line two</pre>
<table><tr><td>Remote</td><td>No</td></tr></table>
<div><img aria-hidden="true" src="x"><p>This is a hands-on role.</p></div>
<input hidden><p>After stray input</p>
<p>Intro<div hidden>x</p>secret</div>
</body></html>'''

JSONLD_MULTILINE_HTML = '''<html><body>
<script type="application/ld+json">
{"@type":"JobPosting","title":"X","description":"Lead a team\\nof 40 engineers across 3 time zones"}
</script>
</body></html>'''

JSONLD_DBLENC_HTML = '''<html><body>
<script type="application/ld+json">
{"@type":"JobPosting","title":"T","description":"&lt;p&gt;Own the roadmap.&lt;/p&gt;&lt;ul&gt;&lt;li&gt;Ship it&lt;/li&gt;&lt;/ul&gt;"}
</script>
</body></html>'''

# HIGH-2 residual: a boundary is invalid if it's alphanumeric, or a ,/. next to more digits.
NUMBER_BOUNDARY_HTML = ('<p>About 2,800 passionate Remitlians work here. He is 2.5 years into '
                         'the role. The range is $1,300,000 total. Growth is at 1.5% this year. '
                         'The full band is $240,000 - $300,000 per year. Say café today.</p>')


def selftest():
    results = []

    def check(name, cond):
        results.append((name, bool(cond)))

    blocks = extract_jsonld_blocks(FIXTURE_HTML)
    check('found three JSON-LD script blocks', len(blocks) == 3)

    items, notes = parse_jsonld_blocks(FIXTURE_HTML)
    check('malformed block skipped, two items parsed', len(items) == 2)
    check('malformed block produced a stderr note', len(notes) == 1)

    jsonld_text = render_jsonld(FIXTURE_HTML)
    check('title extracted', 'Director of Engineering' in jsonld_text)
    check('datePosted extracted', '2026-08-01' in jsonld_text)
    check('organization extracted', 'Acme Corp' in jsonld_text)
    check('location extracted', 'Seattle' in jsonld_text and 'WA' in jsonld_text)
    check('salary extracted', '180000' in jsonld_text and '220000' in jsonld_text)
    check('&amp; unescaped in description', 'hands-on role & it goes' in jsonld_text)
    check('&#8217; unescaped, no raw entities leak', '’s exciting' in jsonld_text
          and '&#8217;' not in jsonld_text and '&amp;' not in jsonld_text)

    visible = render_text(FIXTURE_HTML)
    check('script noise excluded from visible text', 'should not appear' not in visible)
    check('hidden/aria-hidden/display:none subtree excluded', 'requires 10 years management' not in visible)
    check('visible paragraph text present', 'curly' in visible and 'Second paragraph' in visible)

    # HIGH-3: grep corpus excludes formatted labels, non-JobPosting/Article JSON dumps, and
    # never lets a JSON-LD field join with visible text.
    corpus = build_grep_corpus(FIXTURE_HTML, 'auto')
    r = compute_grep_results(corpus, ['Organization: Acme Corp', 'internal blurb never shown',
                                       '"@type":"Organization"',
                                       'exciting. Visible paragraph'], 300)
    check('formatted "Organization:" label not searched', not r[0]['found'])
    check('non-JobPosting/Article JSON-LD field not searched', not r[1]['found'])
    check('raw JSON dump not searched', not r[2]['found'])
    check('JSON-LD text cannot join with visible text', not r[3]['found'])
    r = compute_grep_results(corpus, ["It's exciting"], 300)
    check('genuine JobPosting.description text still found, labeled', r[0]['found']
          and r[0]['label'] == 'jsonld:JobPosting.description')
    text_only_corpus = build_grep_corpus(FIXTURE_HTML, 'text')
    r = compute_grep_results(text_only_corpus, ["It's exciting"], 300)
    check('--mode text excludes JSON-LD from grep', not r[0]['found'])

    # HIGH-1: a phrase must lie inside one block -- can't span list items or heading+paragraph.
    r = compute_grep_results(corpus, ['Lead a team of 40 engineers',
                                       'Requirements 15+ years of experience'], 300)
    check('cross-<li> join rejected', not r[0]['found'])
    check('heading+paragraph join rejected', not r[1]['found'])

    # HIGH-2: word-boundary check, not plain substring.
    r = compute_grep_results(corpus, ['5+ years of experience', 'a remote role'], 300)
    check('substring inside a longer number/word rejected (15+ -> 5+)', not r[0]['found'])
    check('genuine substring at a real word boundary still found (shows negation in context)',
          r[1]['found'] and 'Not a remote role' in r[1]['context'])

    # HIGH-1 residual: the full block-level tag set, not just p/div/li/h*/tr.
    blocks_corpus = build_grep_corpus(BLOCKS_HTML, 'text')
    for phrase, label in [
        ('Lead a team of 40 engineers', 'dl/dd'),
        ('Quoted intro Quote follow-up', 'blockquote+p'),
        ('Header text Main text', 'header+main'),
        ('Nav text After nav', 'nav+p'),
        ('Caption text Footer text', 'figcaption+footer'),
        ('Pre line one Pre line two', 'pre (two lines)'),
        ('Remote No', 'td+td (table cells)'),
    ]:
        r = compute_grep_results(blocks_corpus, [phrase], 300)
        check(f'cross-block join rejected: {label}', not r[0]['found'])
    for phrase, label in [('Pre line one', 'pre line 1'), ('Pre line two', 'pre line 2'),
                           ('Remote', 'td cell 1'), ('No', 'td cell 2')]:
        r = compute_grep_results(blocks_corpus, [phrase], 300)
        check(f'individual block still found: {label}', r[0]['found'])

    # MED regression: void elements (img, input, ...) must never hide their siblings, even
    # with a stray hidden/aria-hidden attribute; a mismatched end tag must not un-hide early.
    r = compute_grep_results(blocks_corpus, ['This is a hands-on role'], 300)
    check('aria-hidden on a void <img> does not hide its sibling <p>', r[0]['found'])
    r = compute_grep_results(blocks_corpus, ['After stray input'], 300)
    check('<input hidden> does not hide the rest of its parent', r[0]['found'])
    r = compute_grep_results(blocks_corpus, ['Intro'], 300)
    check('mismatched nesting: content before the hidden div still found', r[0]['found'])
    r = compute_grep_results(blocks_corpus, ['secret'], 300)
    check('LOW: hidden frame stays hidden through a mismatched </p>, not closed early', not r[0]['found'])

    # HIGH-1 residual: a tag-free JSON-LD field's own literal '\n' is a real block break.
    ml_corpus = build_grep_corpus(JSONLD_MULTILINE_HTML, 'jsonld')
    r = compute_grep_results(ml_corpus, ['Lead a team of 40 engineers'], 300)
    check('tag-free JSON-LD description: embedded newline still blocks a cross-line join', not r[0]['found'])
    r = compute_grep_results(ml_corpus, ['Lead a team'], 300)
    check('tag-free JSON-LD description: first line alone still found', r[0]['found'])

    # LOW (pre-existing): a double-encoded JSON-LD description must decode/strip twice.
    dblenc_corpus = build_grep_corpus(JSONLD_DBLENC_HTML, 'jsonld')
    r = compute_grep_results(dblenc_corpus, ['Own the roadmap', 'Ship it'], 300)
    check('double-encoded JSON-LD description decoded on second pass (1)', r[0]['found'])
    check('double-encoded JSON-LD description decoded on second pass (2)', r[1]['found'])

    # HIGH-2 residual: a boundary is invalid when adjacent is alphanumeric, or a ,/. beside
    # more digits with a digit phrase-edge -- not just "not [A-Za-z0-9]".
    num_corpus = build_grep_corpus(NUMBER_BOUNDARY_HTML, 'text')
    for phrase, label in [
        ('800 passionate Remitlians', 'digit cut out of "2,800" via comma'),
        ('5 years', 'digit cut out of "2.5 years" via period'),
        ('300,000 total', 'digits cut out of "$1,300,000" via comma'),
        ('5%', 'digit cut out of "1.5%" via period'),
        ('000 - $300,000', 'digits cut out of "$240,000" via comma'),
        ('caf', "'caf' must not match inside 'café' (unicode isalnum)"),
    ]:
        r = compute_grep_results(num_corpus, [phrase], 300)
        check(f'number/word boundary rejected: {label}', not r[0]['found'])
    r = compute_grep_results(num_corpus, ['$240,000 - $300,000'], 300)
    check('genuine full number phrase still found', r[0]['found'])

    # rereview.py FAKE: two separate <nav> links must not join into one fabricated sentence,
    # even though an <a> inline inside a shared <p> correctly stays joinable (GENUINE below).
    nav_html = '<nav><a href="/r">Remote</a> <a href="/s">jobs in Seattle</a></nav>'
    nav_corpus = build_grep_corpus(nav_html, 'text')
    r = compute_grep_results(nav_corpus, ['Remote jobs in Seattle'], 300)
    check('two adjacent <nav> links do not join into one fabricated phrase', not r[0]['found'])
    r = compute_grep_results(nav_corpus, ['Remote'], 300)
    check('first <nav> link text alone still found', r[0]['found'])
    inline_link_html = '<p>Apply through <a href="https://x/careers">our careers page</a> before Friday.</p>'
    inline_corpus = build_grep_corpus(inline_link_html, 'text')
    r = compute_grep_results(inline_corpus, ['Apply through our careers page before Friday.'], 300)
    check('an <a> inline within one <p> still joins into its sentence (not a nav link)', r[0]['found'])

    # round-3 HIGH regression: the re-parse-if-output-has-<tag> heuristic must never fire on
    # legitimately escaped text, in EITHER visible text or JSON-LD, and must not eat real
    # cross-block-join protections either.
    escaped_html = '<p>Use std::vector&lt;int&gt; here.</p><ul><li>Lead a team</li><li>of 40 engineers</li></ul>'
    esc_corpus = build_grep_corpus(escaped_html, 'text')
    r = compute_grep_results(esc_corpus, ['std::vector<int>'], 300)
    check('escaped <int>-looking text preserved literally in visible text', r[0]['found'])
    r = compute_grep_results(esc_corpus, ['Lead a team of 40 engineers'], 300)
    check('escaped <tag>-like text does not resurrect a cross-<li> join (visible)', not r[0]['found'])

    jl_escaped = ('<script type="application/ld+json">{"@type":"JobPosting","title":"T",'
                  '"description":"<p>Use std::vector&lt;int&gt; and <ul><li>Lead a team</li>'
                  '<li>of 40 engineers</li></ul></p>"}</script>')
    jl_esc_corpus = build_grep_corpus(jl_escaped, 'jsonld')
    r = compute_grep_results(jl_esc_corpus, ['std::vector<int>'], 300)
    check('escaped <int>-looking text preserved literally in JSON-LD', r[0]['found'])
    r = compute_grep_results(jl_esc_corpus, ['Lead a team of 40 engineers'], 300)
    check('escaped <tag>-like text does not resurrect a cross-<li> join (JSON-LD)', not r[0]['found'])

    # round-3 MED: a JSON-LD HTML value's own embedded '\n'/'\r\n' is just whitespace, not a
    # block break -- only a genuinely tag-free plain-text value treats '\n' as one.
    for raw, label in [
        ('<p>This is a hands-on\nrole.</p>', 'JSON-LD HTML description with embedded \\n'),
        ('<p>This is a hands-on\r\nrole.</p>', 'JSON-LD HTML description with embedded \\r\\n'),
    ]:
        blocks = jsonld_field_to_blocks(raw)
        check(f'{label}: newline is whitespace, not a block break', blocks == ['This is a hands-on role.'])
    plain_blocks = jsonld_field_to_blocks('Requirements:\nLead a team\nof 40 engineers')
    check('JSON-LD plain-text value: its own newline IS a block break',
          plain_blocks == ['Requirements:', 'Lead a team', 'of 40 engineers'])

    # round-3 MED: implicit end tags for optional-close elements, so a never-closed hidden
    # p/li/dt/dd/td/th/tr/option doesn't hide the rest of the page.
    implicit_close_cases = [
        ('<div><p hidden>Hidden note<p>This is a hands-on role.</p></div>',
         'This is a hands-on role.', '<p hidden> auto-closed by the next <p>'),
        ('<ul><li hidden>Old requirement<li>8+ years of leadership</ul>',
         '8+ years of leadership', '<li hidden> auto-closed by the next <li>'),
        ('<table><tr><td hidden>x<td>Visible cell text</tr></table><p>After table</p>',
         'After table', 'hidden <td> with no </td>, closed at table end'),
        ('<dl><dt hidden>Term<dd>Visible definition</dl>',
         'Visible definition', 'hidden <dt> auto-closed by sibling <dd>'),
        ('<select><option hidden>A</select><p>After select</p>',
         'After select', 'hidden <option> auto-closed at </select>'),
    ]
    for html_in, phrase, label in implicit_close_cases:
        r = compute_grep_results(build_grep_corpus(html_in, 'text'), [phrase], 300)
        check(f'implicit close: {label}', r[0]['found'])

    # round-3 LOW: an unclosed <nav> must not scope every later inline link on the page.
    unclosed_nav_html = ('<body><nav><a href="/h">Home</a><main><p>Apply through '
                          '<a href="/c">our careers page</a> before Friday.</p></main></body>')
    r = compute_grep_results(build_grep_corpus(unclosed_nav_html, 'text'),
                              ['Apply through our careers page before Friday.'], 300)
    check('unclosed <nav> implicitly closed by <main>, later inline link still joins', r[0]['found'])

    # round-4 LOW: Indian-style digit grouping (2-digit groups after the first) must also be
    # protected, not just the Western 3-digit convention.
    r = compute_grep_results(build_grep_corpus('<p>Revenue is $1,300,000 total.</p>', 'text'),
                              ['300,000 total'], 300)
    check('genuine Western 3-digit thousands group still rejected', not r[0]['found'])
    r = compute_grep_results(build_grep_corpus('<p>The amount is 12,34,567 INR total.</p>', 'text'),
                              ['34,567 INR'], 300)
    check('Indian-style 2-digit group also rejected (round-4 LOW)', not r[0]['found'])
    # DEVIATION (documented, per the coordinator's explicit instruction to prefer this):
    # accepting the Indian-grouping fix now also rejects a genuine comma-separated list that
    # happens to have 2-3 digit items, since digits alone can't tell the two apart.
    r = compute_grep_results(build_grep_corpus('<p>Item sizes 20,30,40 are available.</p>', 'text'),
                              ['sizes 20'], 300)
    check('DEVIATION: comma-separated list item now also rejected (Indian-grouping tradeoff)',
          not r[0]['found'])

    # round-4 MED: <br> must stay a block separator but must NOT implicitly close a <p> (only
    # the real HTML "closes a p" tag set does; <hr> is in that set and still closes it).
    for html_in, label in [
        ('<div><p hidden>note<br>secret after br</p></div>', 'hidden attribute'),
        ('<div><p style="display:none">note<br>secret after br</p></div>', 'display:none'),
        ('<div><p aria-hidden="true">note<br>secret after br</p></div>', 'aria-hidden'),
    ]:
        r = compute_grep_results(build_grep_corpus(html_in, 'text'), ['secret after br'], 300)
        check(f'<br> does not implicitly close a hidden <p> ({label})', not r[0]['found'])
    jl_hidden_br = ('<script type="application/ld+json">{"@type":"JobPosting","title":"T",'
                    '"description":"<div><p hidden>note<br>secret after br</p></div>"}</script>')
    r = compute_grep_results(build_grep_corpus(jl_hidden_br, 'jsonld'), ['secret after br'], 300)
    check('<br> does not implicitly close a hidden <p> (JSON-LD HTML)', not r[0]['found'])
    r = compute_grep_results(build_grep_corpus('<p>note<br>still visible</p>', 'text'),
                              ['note still visible'], 300)
    check('<br> in a VISIBLE paragraph still separates blocks as before', not r[0]['found'])
    r = compute_grep_results(build_grep_corpus('<p hidden>a<hr>b', 'text'), ['b'], 300)
    check('<hr> still implicitly closes a hidden <p> (unaffected)', r[0]['found'])

    # round-4 MED: a plain-text value that merely MENTIONS a tag name (no matched pair, no
    # block tag) must not be classified as HTML -- its newlines stay meaningful breaks, and
    # the literal tag-like text must survive untouched.
    bare_tag_mention = 'Know <b> vs <strong>\nLead a team\nof 40 engineers'
    blocks = jsonld_field_to_blocks(bare_tag_mention)
    check('bare unmatched <b>/<strong> mention classified as plain text (not HTML)',
          blocks == ['Know <b> vs <strong>', 'Lead a team', 'of 40 engineers'])
    r = compute_grep_results([('jsonld', b) for b in blocks], ['Lead a team of 40 engineers'], 300)
    check('plain-text newline still a block break despite the bare tag mention', not r[0]['found'])
    check('_looks_like_html: bare unmatched inline tag mention is NOT html',
          not _looks_like_html('Know <b> vs <strong>'))
    check('_looks_like_html: a real MATCHED inline pair IS html', _looks_like_html('a <b>bold</b> word'))
    check('_looks_like_html: a bare block tag IS html (no pair needed)', _looks_like_html('open <div> only'))
    check('_looks_like_html: a bare <br> IS html (no pair needed, no closing tag exists)',
          _looks_like_html('line one <br> line two'))

    # round-5 MED: inline-only markup (matched pairs like <b>/<strong>/<a>, or a bare <br>)
    # must NOT switch a JSON-LD value into "newline is just whitespace" mode -- only a real
    # block-level tag does that.
    for value, fake_phrase, label in [
        ('<b>Requirements</b>\nLead a team\nof 40 engineers', 'Lead a team of 40 engineers',
         'inline <b> pair + newlines'),
        ('…\n\n<strong>You Have:</strong>\n8+ years of leadership\nHistory building platforms',
         '8+ years of leadership History building platforms', 'inline <strong> pair + blank line'),
        ('Apply <a>here</a>\nNot a remote role', 'here Not a remote role', 'inline <a> pair'),
    ]:
        blocks = jsonld_field_to_blocks(value)
        r5_corpus = [('jsonld', b) for b in blocks]
        r = compute_grep_results(r5_corpus, [fake_phrase], 300)
        check(f'{label}: newline still a real break, fabricated join rejected', not r[0]['found'])
    check('inline <b> tag itself still stripped from the text',
          'Requirements' in jsonld_field_to_blocks('<b>Requirements</b>\nLead a team')
          and not any('<b>' in b for b in jsonld_field_to_blocks('<b>Requirements</b>\nLead a team')))
    r = compute_grep_results([('jsonld', b) for b in jsonld_field_to_blocks(
        '…\n\n<strong>You Have:</strong>\n8+ years of leadership\nHistory building platforms')],
        ['You Have:'], 300)
    check('blank line (\\n\\s*\\n) is always a break, even with only inline markup', r[0]['found'])

    # round-5: the earlier keep-case must still hold -- a real block tag (<p>) makes a lone
    # embedded '\n' ordinary whitespace, not a break.
    keep_blocks = jsonld_field_to_blocks('<p>This is a hands-on\nrole.</p>')
    check('round-5 keep-case: <p> block tag makes a lone \\n plain whitespace',
          keep_blocks == ['This is a hands-on role.'])

    # MED: empty/whitespace phrase is an input error (exit 2 via main), not a match.
    for bad_phrase in ('', '   '):
        try:
            validate_phrases([bad_phrase])
            check(f'empty/whitespace phrase {bad_phrase!r} rejected', False)
        except ValueError:
            check(f'empty/whitespace phrase {bad_phrase!r} rejected', True)
    validate_phrases(['a real phrase'])  # must not raise

    # MED: content-type gate.
    check('text/html allowed', _check_content_type('text/html; charset=utf-8') is None)
    check('missing content-type allowed (permissive default)', _check_content_type('') is None)
    for bad in ('application/pdf', 'image/png'):
        try:
            _check_content_type(bad)
            check(f'{bad} rejected', False)
        except FetchError:
            check(f'{bad} rejected', True)

    # MED: <meta charset> honoured only when the header gave none.
    check('meta charset sniffed from head bytes', sniff_meta_charset(CP1252_META_HTML) == 'windows-1252')
    check('header charset wins over sniffing', _decode('café'.encode('latin-1'), 'latin-1') == 'café')

    # LOW: an unclosed <head> must not swallow <body>.
    check('unclosed <head> does not hide <body>', 'visible body phrase' in html_to_text(NOHEAD_HTML))

    # MED: fetch() turns every anticipated failure into a clean FetchError, never a traceback.
    orig_urlopen = urllib.request.urlopen
    for exc, name in [
        (urllib.error.HTTPError('http://x', 404, 'Not Found', {}, None), 'HTTPError'),
        (urllib.error.URLError('boom'), 'URLError'),
        (TimeoutError('timed out'), 'TimeoutError'),
        (ValueError('unknown url type'), 'ValueError'),
        (EOFError('Compressed file ended before the end-of-stream marker was reached'), 'EOFError'),
        (gzip.BadGzipFile('not a gzipped file'), 'gzip.BadGzipFile'),
        (http.client.IncompleteRead(b''), 'http.client.IncompleteRead'),
    ]:
        def _raise(*a, _exc=exc, **kw):
            raise _exc
        urllib.request.urlopen = _raise
        try:
            fetch('http://example.invalid/x')
            ok = False
        except FetchError:
            ok = True
        except Exception:
            ok = False
        check(f'fetch() converts {name} to a clean FetchError (exit 2), not a traceback', ok)
    urllib.request.urlopen = orig_urlopen

    # grep exit-code contract.
    ok_results = compute_grep_results(corpus, ["It's exciting"], 300)
    bad_results = compute_grep_results(corpus, ['this phrase does not exist anywhere'], 300)
    check('grep exit code 0 when all found', grep_exit_code(ok_results) == 0)
    check('grep exit code 1 when any phrase missing', grep_exit_code(bad_results) == 1)
    check('format_grep_results renders NOT FOUND', 'NOT FOUND' in format_grep_results(bad_results))
    check('format_grep_results labels the FOUND source', '[jsonld:JobPosting.description]'
          in format_grep_results(ok_results))

    ok = True
    for name, cond in results:
        print(('PASS ' if cond else 'FAIL ') + name)
        ok = ok and cond
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0],
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('url', nargs='?')
    ap.add_argument('--grep', action='append', default=[], metavar='PHRASE')
    ap.add_argument('--mode', choices=['auto', 'jsonld', 'text'], default='auto')
    ap.add_argument('--context', type=int, default=300,
                     help='max chars of the enclosing block to show around a match (default 300)')
    ap.add_argument('--out')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    if args.selftest:
        sys.exit(0 if selftest() else 1)

    if not args.url:
        ap.error('URL is required (unless --selftest)')

    try:
        validate_phrases(args.grep)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)

    try:
        html_text, _ = fetch(args.url)
        if args.grep:
            grep_results = compute_grep_results(build_grep_corpus(html_text, args.mode),
                                                 args.grep, args.context)
            output = format_grep_results(grep_results)
        else:
            if args.mode == 'auto':
                sections = [f'=== JSON-LD ===\n{render_jsonld(html_text)}',
                            f'=== TEXT ===\n{render_text(html_text)}']
            elif args.mode == 'jsonld':
                sections = [render_jsonld(html_text)]
            else:
                sections = [render_text(html_text)]
            output = '\n\n'.join(sections)
    except FetchError as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f'unexpected error: {e}', file=sys.stderr)
        sys.exit(2)

    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(output + '\n')
    else:
        print(output)

    sys.exit(grep_exit_code(grep_results) if args.grep else 0)


if __name__ == '__main__':
    main()
