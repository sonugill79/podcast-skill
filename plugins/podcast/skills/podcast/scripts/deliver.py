#!/usr/bin/env python3
"""
deliver.py: send a rendered episode to the owner's Telegram, safely.

Episode content is often private (job searches, compensation) -- this refuses to upload
to any chat other people could read unless explicitly forced with --allow-shared.

  deliver.py AUDIO --bot NAME [--chat ID] [--title T] [--performer P] [--caption TEXT]
             [--chapters FILE] [--allow-shared] [--dry-run] [--selftest]

  deliver.py episode.mp3 --bot pip --dry-run
      -> runs the privacy gate and prints what would be sent; sends nothing

Config: ~/.config/telegram-send/bots.json -> {"<name>": {"token": "...", "default_chat_id": "..."}}
Optional owner allowlist: ~/.config/topic-podcast/deliver.json ->
    {"owner_user_ids": [123456]}  (preferred: matches getChat.id / admin.user.id, takes precedence)
    {"owner_usernames": ["your-telegram-handle"]}  (matched case-insensitively, exact equality)
If the file exists it must be one of those shapes (non-empty list of the right type) or the
gate refuses outright (exit 3) -- a typo'd key must not silently fall back to count-only.
Neither config file is created or edited by this script.

Exit codes: 0 ok · 3 privacy gate refused (or owner config present but malformed) ·
4 audio file over the 50 MB Bot API limit · 5 chapters file present but invalid · 1 other error.
"""
import argparse, json, math, os, re, subprocess, sys, tempfile
import urllib.error, urllib.parse, urllib.request, uuid

BOTS_CONFIG = os.path.expanduser('~/.config/telegram-send/bots.json')
OWNER_CONFIG = os.path.expanduser('~/.config/topic-podcast/deliver.json')
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_CAPTION = 1024
TOKEN_RE = re.compile(r'bot\d+(?::|%3[Aa])[A-Za-z0-9_-]+')


class DeliverError(Exception):
    pass


class OwnerConfigError(Exception):
    pass


class ChaptersError(Exception):
    pass


def redact(text, token=None):
    s = str(text)
    if token:
        s = s.replace(f'bot{token}', 'bot<redacted>')  # avoid a leftover "bot" -> "botbot<redacted>"
        s = s.replace(token, 'bot<redacted>')           # any bare occurrence without the "bot" prefix
    return TOKEN_RE.sub('bot<redacted>', s)


def load_bots():
    with open(BOTS_CONFIG, encoding='utf-8') as f:
        return json.load(f)


def load_owner_config():
    """Returns None if OWNER_CONFIG doesn't exist (caller applies count-rule-only). Raises
    OwnerConfigError if it exists but is malformed -- a typo'd key or wrong shape must refuse,
    never silently fall back. Otherwise returns {'user_ids': set[int]|None, 'usernames': set[str]|None}
    (lowercased), with user_ids taking precedence over usernames when both are present."""
    try:
        with open(OWNER_CONFIG, encoding='utf-8') as f:
            raw = f.read()
    except FileNotFoundError:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise OwnerConfigError(f'{OWNER_CONFIG} is not valid JSON: {e}')
    if not isinstance(data, dict):
        raise OwnerConfigError(f'{OWNER_CONFIG} must be a JSON object')
    has_ids, has_names = 'owner_user_ids' in data, 'owner_usernames' in data
    if not has_ids and not has_names:
        raise OwnerConfigError(f'{OWNER_CONFIG} has neither "owner_user_ids" nor "owner_usernames"')
    result = {'user_ids': None, 'usernames': None}
    if has_ids:
        ids = data['owner_user_ids']
        if (not isinstance(ids, list) or not ids
                or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids)):
            raise OwnerConfigError('"owner_user_ids" must be a non-empty list of integers')
        result['user_ids'] = set(ids)
    if has_names:
        names = data['owner_usernames']
        if (not isinstance(names, list) or not names
                or not all(isinstance(n, str) and n.strip() for n in names)):
            raise OwnerConfigError('"owner_usernames" must be a non-empty list of non-empty strings')
        result['usernames'] = {n.lower() for n in names}
    return result


def api_call(token, method, params=None, timeout=30):
    url = f'https://api.telegram.org/bot{token}/{method}'
    data = urllib.parse.urlencode(params).encode() if params else None
    req = urllib.request.Request(url, data=data)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        desc = None
        try:
            desc = json.loads(e.read().decode('utf-8', errors='replace')).get('description')
        except Exception:
            pass
        msg = f'{method} failed: HTTP {e.code} {e.reason}' + (f' -- {desc}' if desc else '')
        raise DeliverError(redact(msg, token))
    except Exception as e:
        raise DeliverError(redact(f'{method} failed: {e}', token))
    if not isinstance(body, dict):
        raise DeliverError(redact(f'{method}: unexpected response shape (not an object)', token))
    if not body.get('ok'):
        raise DeliverError(redact(f'{method} failed: {body.get("description")}', token))
    if 'result' not in body:
        raise DeliverError(redact(f'{method}: response missing "result"', token))
    return body['result']


# ---- privacy gate (pure function over the three read-only API payloads) ----

def _admins_well_formed(admins_list):
    """A malformed admin entry (not a dict, missing/non-dict 'user', or a non-int user.id)
    must fail the WHOLE gate closed rather than being silently dropped from consideration --
    dropping it let a legitimate co-owner mask a broken/unreadable entry (round-1 regression)."""
    for a in admins_list:
        if not isinstance(a, dict):
            return False
        user = a.get('user')
        if not isinstance(user, dict):
            return False
        uid = user.get('id')
        if not isinstance(uid, int) or isinstance(uid, bool):
            return False
    return True


def privacy_decision(chat, member_count, admins, owner_config):
    """chat: getChat result (dict). member_count: getChatMemberCount result or None (private
    chats never call it). admins: getChatAdministrators result or []. owner_config: None
    (unconfigured -> count/type rule only) or {'user_ids': set|None, 'usernames': set|None}
    from load_owner_config(). Returns (allowed: bool, reason: str, rule: str|None) where rule
    names which check decided an allow ('count-only' | 'owner_user_ids' | 'owner_usernames')."""
    ctype = chat.get('type')

    if ctype == 'private':
        if owner_config is None:
            return True, 'private chat (owners unconfigured, no identity check)', 'count-only'
        if owner_config['user_ids'] is not None:
            cid = chat.get('id')
            if type(cid) is int and cid in owner_config['user_ids']:
                return True, f'private chat, id {cid} is an owner', 'owner_user_ids'
            return False, f'private chat id {cid!r} is not in owner_user_ids', 'owner_user_ids'
        uname = chat.get('username')
        if isinstance(uname, str) and uname.lower() in owner_config['usernames']:
            return True, f'private chat, username "{uname}" is an owner', 'owner_usernames'
        return False, f'private chat username {uname!r} is not in owner_usernames', 'owner_usernames'

    if ctype in ('group', 'supergroup'):
        if chat.get('username'):
            return False, f'{ctype} is public (has username "{chat.get("username")}")', None
        if chat.get('join_by_request'):
            return False, f'{ctype} allows join-by-request (not a closed chat)', None
        if chat.get('invite_link'):
            return False, f'{ctype} has an invite_link set', None
        if type(member_count) is not int or member_count > 2:
            return False, f'{ctype} has {member_count!r} members (limit is 2: bot + one human)', None
        if owner_config is None:
            return True, f'{ctype} with {member_count} members (owners unconfigured, count rule only)', 'count-only'
        admins_list = admins if isinstance(admins, list) else []
        if not _admins_well_formed(admins_list):
            return False, f'{ctype} has a malformed administrator entry', None
        humans = [a for a in admins_list if not a['user'].get('is_bot')]
        if not humans:
            return False, f'{ctype} has no human administrators', None
        if owner_config['user_ids'] is not None:
            ids = [h['user'].get('id') for h in humans]
            bad = [i for i in ids if type(i) is not int or i not in owner_config['user_ids']]
            if bad:
                return False, f'{ctype} has non-owner administrator ids: {bad}', 'owner_user_ids'
            return True, f'{ctype} with {member_count} members, all human admins are owners (ids)', 'owner_user_ids'
        names = [h['user'].get('username') for h in humans]
        bad = [n for n in names if not (isinstance(n, str) and n.lower() in owner_config['usernames'])]
        if bad:
            return False, f'{ctype} has non-owner administrators: {bad}', 'owner_usernames'
        return True, f'{ctype} with {member_count} members, all human admins are owners (usernames)', 'owner_usernames'

    return False, f'chat type "{ctype}" is not allowed', None


def gate_with_bypass(chat, member_count, admins, owner_config, allow_shared):
    allowed, reason, rule = privacy_decision(chat, member_count, admins, owner_config)
    if not allowed and allow_shared:
        return True, f'WARNING: privacy gate bypassed ({reason})', rule
    return allowed, reason, rule


def run_privacy_gate(token, chat_id, owner_config, allow_shared):
    chat = api_call(token, 'getChat', {'chat_id': chat_id})
    if not isinstance(chat, dict):
        raise DeliverError('getChat: unexpected result shape (not an object)')
    member_count, admins = None, []
    if chat.get('type') in ('group', 'supergroup'):
        member_count = api_call(token, 'getChatMemberCount', {'chat_id': chat_id})
        admins = api_call(token, 'getChatAdministrators', {'chat_id': chat_id})
    allowed, reason, rule = gate_with_bypass(chat, member_count, admins, owner_config, allow_shared)
    return chat, member_count, admins, allowed, reason, rule


def admin_identity_summary(chat, admins):
    """Human-readable identity info for --dry-run: admin ids for a group, chat id for private."""
    if chat.get('type') in ('group', 'supergroup'):
        humans = [a['user'] for a in (admins if isinstance(admins, list) else [])
                  if isinstance(a, dict) and isinstance(a.get('user'), dict) and not a['user'].get('is_bot')]
        if not humans:
            return '(no human administrators)'
        return ', '.join(f'{h.get("username") or "?"}(id={h.get("id")})' for h in humans)
    return f'id={chat.get("id")}'


# ---- formatting helpers ----

def fmt_mmss(seconds):
    total = int(seconds)
    m, s = divmod(total, 60)
    return f'{m}:{s:02d}'


def _utf16_len(s):
    return len(s.encode('utf-16-le')) // 2


def truncate_caption(caption, limit=MAX_CAPTION):
    """Truncates by UTF-16 code units (what Telegram counts), never splitting a surrogate pair."""
    if caption is None or _utf16_len(caption) <= limit:
        return caption
    encoded = caption.encode('utf-16-le')
    cut = (limit - 1) * 2
    while cut > 0:
        try:
            return encoded[:cut].decode('utf-16-le') + '…'
        except UnicodeDecodeError:
            cut -= 2
    return '…'


def sanitize_filename(name):
    return re.sub(r'[^A-Za-z0-9._-]', '_', name)


def format_chapters_message(data):
    lines = ['Chapters:']
    for ch in data['chapters']:
        lines.append(f'{fmt_mmss(ch["start"])}  {ch["title"]}')
    return '\n'.join(lines)


def load_and_validate_chapters(path):
    """Loads and fully validates a chapters file, BEFORE the gate or any upload -- a bad file
    must never deliver the audio, drop the chapters, and leave a retry to duplicate the audio."""
    try:
        with open(path, encoding='utf-8') as f:
            raw = f.read()
    except OSError as e:
        raise ChaptersError(f'{path}: {e}')
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ChaptersError(f'{path}: invalid JSON ({e})')
    if not isinstance(data, dict) or not isinstance(data.get('chapters'), list) or not data['chapters']:
        raise ChaptersError(f'{path}: must be a JSON object with a non-empty "chapters" list')
    chapters = []
    for i, ch in enumerate(data['chapters']):
        if not isinstance(ch, dict):
            raise ChaptersError(f'{path}: chapters[{i}] is not an object')
        start = ch.get('start')
        if isinstance(start, bool) or not isinstance(start, (int, float)):
            raise ChaptersError(f'{path}: chapters[{i}].start must be a number')
        if not math.isfinite(start):
            raise ChaptersError(f'{path}: chapters[{i}].start must be finite')
        if start < 0:
            raise ChaptersError(f'{path}: chapters[{i}].start must not be negative')
        title = ch.get('title')
        if not isinstance(title, str) or not title:
            raise ChaptersError(f'{path}: chapters[{i}].title must be a non-empty string')
        chapters.append({'start': float(start), 'title': title})
    result = {'chapters': chapters}
    formatted_len = _utf16_len(format_chapters_message(result))
    if formatted_len > 4096:
        raise ChaptersError(f'{path}: formatted chapters message is {formatted_len} UTF-16 units, '
                             f"over Telegram's 4096-char sendMessage limit")
    return result


def resolve_chapters_path(audio_path, explicit):
    if explicit:
        return explicit
    guess = os.path.splitext(audio_path)[0] + '.chapters.json'
    return guess if os.path.exists(guess) else None


# ---- multipart/form-data, built by hand ----

def build_multipart(fields, file_field, filename, content_type, file_bytes):
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        if value is None:
            continue
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
            .encode('utf-8'))
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; '
        f'filename="{filename}"\r\nContent-Type: {content_type}\r\n\r\n'.encode('utf-8'))
    parts.append(file_bytes)
    parts.append(f'\r\n--{boundary}--\r\n'.encode('utf-8'))
    return b''.join(parts), boundary


def send_audio(token, chat_id, audio_path, title, performer, duration, caption):
    with open(audio_path, 'rb') as f:
        file_bytes = f.read()
    fields = {'chat_id': chat_id, 'title': title, 'performer': performer, 'duration': str(duration)}
    if caption:
        fields['caption'] = caption
    filename = sanitize_filename(os.path.basename(audio_path))
    body, boundary = build_multipart(fields, 'audio', filename, 'audio/mpeg', file_bytes)
    req = urllib.request.Request(f'https://api.telegram.org/bot{token}/sendAudio', data=body)
    req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            result = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        desc = None
        try:
            desc = json.loads(e.read().decode('utf-8', errors='replace')).get('description')
        except Exception:
            pass
        msg = f'sendAudio failed: HTTP {e.code} {e.reason}' + (f' -- {desc}' if desc else '')
        raise DeliverError(redact(msg, token))
    except Exception as e:
        raise DeliverError(redact(f'sendAudio failed: {e}', token))
    if not isinstance(result, dict) or not result.get('ok') or 'result' not in result:
        raise DeliverError(redact(f'sendAudio failed: {result.get("description") if isinstance(result, dict) else result}', token))
    return result['result']


def get_duration_seconds(path):
    out = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path],
        capture_output=True, text=True, check=True)
    return round(float(out.stdout.strip()))


# ---- selftest ----

def selftest():
    results = []

    def check(name, cond):
        results.append((name, bool(cond)))

    OWNERS_NAMES = {'user_ids': None, 'usernames': {'owner-handle'}}
    OWNERS_IDS = {'user_ids': {555}, 'usernames': None}
    priv_owner = {'type': 'private', 'id': 555, 'username': 'owner-handle'}
    priv_other = {'type': 'private', 'id': 999, 'username': 'randomuser'}
    priv_no_username = {'type': 'private', 'id': 999}
    admins_ok = [{'user': {'id': 1, 'is_bot': True, 'username': 'mybot'}},
                 {'user': {'id': 555, 'is_bot': False, 'username': 'owner-handle'}}]
    admins_bad = [{'user': {'id': 1, 'is_bot': True, 'username': 'mybot'}},
                  {'user': {'id': 2, 'is_bot': False, 'username': 'someoneelse'}}]
    group = {'type': 'group', 'title': 'Reports'}
    public_group = {'type': 'supergroup', 'title': 'Reports', 'username': 'public_grp'}
    channel = {'type': 'channel', 'title': 'Public Channel'}

    a, r, rule = privacy_decision(priv_owner, None, [], OWNERS_NAMES)
    check('private + owner username -> allowed', a and rule == 'owner_usernames')
    a, r, rule = privacy_decision(priv_other, None, [], OWNERS_NAMES)
    check('private + non-owner username -> refused', not a)
    a, r, rule = privacy_decision(priv_no_username, None, [], OWNERS_NAMES)
    check('private + no username, owners by name configured -> refused', not a)
    a, r, rule = privacy_decision(group, 2, admins_ok, OWNERS_NAMES)
    check('group, 2 members, owner admin -> allowed', a)
    a, r, rule = privacy_decision(group, 3, admins_ok, OWNERS_NAMES)
    check('group, 3 members -> refused', not a)
    a, r, rule = privacy_decision(channel, None, [], OWNERS_NAMES)
    check('channel -> refused', not a)
    a, r, rule = privacy_decision(group, 2, admins_bad, OWNERS_NAMES)
    check('group, 2 members, non-owner human admin -> refused', not a)
    a, r, rule = privacy_decision(group, 2, admins_bad, None)
    check('no owner config -> count rule only, allowed', a and rule == 'count-only')
    a, r, rule = privacy_decision(public_group, 2, admins_ok, OWNERS_NAMES)
    check('public supergroup (has username) -> refused even with 2 members + owner admin', not a)
    a, r, rule = privacy_decision({**group, 'join_by_request': True}, 2, admins_ok, OWNERS_NAMES)
    check('join_by_request group -> refused', not a)
    a, r, rule = privacy_decision({**group, 'invite_link': 'https://t.me/x'}, 2, admins_ok, OWNERS_NAMES)
    check('group with invite_link -> refused', not a)
    a, r, rule = privacy_decision(group, True, admins_ok, OWNERS_NAMES)  # JSON true is not an int
    check('member_count == True (bool, not int) -> refused', not a)
    a, r, rule = privacy_decision(group, '2', admins_ok, OWNERS_NAMES)
    check('member_count == "2" (string) -> refused', not a)

    a, r, rule = privacy_decision(priv_owner, None, [], OWNERS_IDS)
    check('private + owner_user_ids match -> allowed', a and rule == 'owner_user_ids')
    a, r, rule = privacy_decision(priv_other, None, [], OWNERS_IDS)
    check('private + owner_user_ids, id not an owner -> refused', not a)
    admins_id_ok = [{'user': {'id': 1, 'is_bot': True}}, {'user': {'id': 555, 'is_bot': False, 'username': 'x'}}]
    a, r, rule = privacy_decision(group, 2, admins_id_ok, OWNERS_IDS)
    check('group admin id matches owner_user_ids (username irrelevant) -> allowed', a and rule == 'owner_user_ids')

    # round-2 regression: a malformed admin entry must fail the WHOLE gate closed, even
    # when a legitimate owner is also present in the same list (it must not be silently
    # dropped from consideration).
    a, r, rule = privacy_decision(group, 2, [admins_id_ok[1], {'status': 'administrator'}], OWNERS_IDS)
    check('owner present + one non-dict-shaped admin entry -> refused, not silently dropped', not a)
    a, r, rule = privacy_decision(group, 2, [admins_id_ok[1], {'user': None}], OWNERS_IDS)
    check('owner present + admin entry with user=null -> refused', not a)
    a, r, rule = privacy_decision(group, 2, [admins_id_ok[1], {'user': {'is_bot': False, 'username': 'x'}}], OWNERS_IDS)
    check('owner present + admin entry with non-int user.id (missing) -> refused', not a)
    a, r, rule = privacy_decision(group, 2, [admins_id_ok[1], {'user': {'id': '9', 'is_bot': False}}], OWNERS_IDS)
    check('owner present + admin entry with string user.id -> refused', not a)

    a, r, rule = privacy_decision(channel, None, [], OWNERS_NAMES)
    a2, r2, rule2 = gate_with_bypass(channel, None, [], OWNERS_NAMES, allow_shared=True)
    check('--allow-shared bypasses a refusal', a2 and not a)
    check('--allow-shared reason is loud', r2.startswith('WARNING: privacy gate bypassed'))

    import inspect
    src = inspect.getsource(privacy_decision)
    check('privacy_decision has no I/O', not any(w in src for w in ('api_call', 'open(', 'print(', 'os.', 'global ')))

    for shape, label in [
        ('{"owner_usernames": "owner-handle"}', 'owner_usernames as a bare string'),
        ('{"owner_usernames": [null]}', 'owner_usernames list containing null'),
        ('{"owner_usernames": []}', 'owner_usernames empty list'),
        ('{"owner_user_ids": ["555"]}', 'owner_user_ids list of strings, not ints'),
        ('{"owner_username": ["owner-handle"]}', 'typo\'d key "owner_username"'),
        ('not json', 'malformed JSON'),
        ('[]', 'top-level list, not object'),
    ]:
        global OWNER_CONFIG
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
            f.write(shape)
            tmp_path = f.name
        saved = OWNER_CONFIG
        OWNER_CONFIG = tmp_path
        try:
            load_owner_config()
            check(f'malformed owner config rejected: {label}', False)
        except OwnerConfigError:
            check(f'malformed owner config rejected: {label}', True)
        finally:
            OWNER_CONFIG = saved
            os.remove(tmp_path)

    body, boundary = build_multipart({'chat_id': '123', 'title': 'Ep'}, 'audio', 'ep.mp3',
                                      'audio/mpeg', b'FAKEAUDIOBYTES')
    check('multipart starts with boundary', body.startswith(f'--{boundary}\r\n'.encode()))
    check('multipart ends with closing boundary', body.endswith(f'--{boundary}--\r\n'.encode()))
    check('multipart has field CRLF framing', b'\r\n\r\n123\r\n' in body)
    check('multipart has file part headers', b'filename="ep.mp3"' in body
          and b'Content-Type: audio/mpeg' in body)
    check('multipart embeds raw file bytes', b'FAKEAUDIOBYTES' in body)
    check('sanitize_filename strips quote/CR/LF', sanitize_filename('we"ird\r\nname.mp3') == 'we_ird__name.mp3')
    check('sanitize_filename keeps normal names untouched', sanitize_filename('my-episode-name.mp3')
          == 'my-episode-name.mp3')

    token = 'bot123456:ABC-def_XYZ789'
    bare_token = '123456:ABC-def_XYZ789'
    msg = f'HTTP Error 404: Not Found for url https://api.telegram.org/{token}/sendAudio'
    red = redact(msg, bare_token)
    check('redactor strips known token, no double "bot" prefix', bare_token not in red
          and 'bot<redacted>' in red and 'botbot<redacted>' not in red)
    red2 = redact('failed calling bot987654321:AAHH_some-token/getChat')
    check('redactor strips token by pattern alone', 'bot<redacted>' in red2 and 'AAHH_some-token' not in red2)
    red3 = redact('url https://api.telegram.org/bot123%3AABC/getChat')
    check('redactor strips URL-encoded colon form', 'ABC' not in red3)

    check('fmt_mmss(0) == 0:00', fmt_mmss(0) == '0:00')
    check('fmt_mmss(3599.9) == 59:59 (truncates)', fmt_mmss(3599.9) == '59:59')

    short_caption = 'short caption'
    long_caption = 'x' * 1100
    check('short caption unchanged', truncate_caption(short_caption) == short_caption)
    trunc = truncate_caption(long_caption)
    check('long caption truncated to limit (chars) with ellipsis',
          len(trunc) == MAX_CAPTION and trunc.endswith('…'))
    emoji_caption = '\U0001F4B8' * 1024  # astral (2 UTF-16 units each) -> 2048 units, over the limit
    trunc_emoji = truncate_caption(emoji_caption)
    check('astral-emoji caption truncated by UTF-16 units, no split surrogate pair',
          _utf16_len(trunc_emoji) <= MAX_CAPTION)

    for content, label, should_fail in [
        ('{"chapters": [', 'malformed JSON', True),
        (json.dumps({'chapters': [{'start': -5, 'title': 'neg'}]}), 'negative start', True),
        ('{"chapters": [{"start": NaN, "title": "n"}]}', 'NaN start', True),
        ('{"chapters": [{"start": Infinity, "title": "i"}]}', 'Infinity start', True),
        (json.dumps({'chapters': [{'start': '1:30', 'title': 's'}]}), 'string start', True),
        (json.dumps({'chapters': [{'start': 3}]}), 'missing title', True),
        (json.dumps([{'start': 0, 'title': 'x'}]), 'top-level list', True),
        (json.dumps({'chapters': []}), 'empty chapters list', True),
        (json.dumps({'chapters': [{'start': 0, 'title': 'Intro'}, {'start': 75, 'title': 'Comp'}]}),
         'valid chapters', False),
        (json.dumps({'chapters': [{'start': i, 'title': 'x' * 1000} for i in range(5)]}),
         'formatted message over 4096 chars (Telegram sendMessage limit)', True),
        (json.dumps({'chapters': [{'start': 0, 'title': '\U0001F4B8' * 2100}]}),
         'formatted message under 4096 Python chars but over 4096 UTF-16 units (emoji)', True),
    ]:
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
            f.write(content)
            tmp_path = f.name
        try:
            load_and_validate_chapters(tmp_path)
            check(f'chapters validation: {label}', not should_fail)
        except ChaptersError:
            check(f'chapters validation: {label}', should_fail)
        finally:
            os.remove(tmp_path)
    good_data = {'chapters': [{'start': 0, 'title': 'Intro'}, {'start': 75.9, 'title': 'Comp'},
                               {'start': 3600, 'title': 'Hour'}]}
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
        json.dump(good_data, f)
        with_tmp = f.name
    validated = load_and_validate_chapters(with_tmp)
    os.remove(with_tmp)
    check('chapters message format m:ss  title', format_chapters_message(validated)
          == 'Chapters:\n0:00  Intro\n1:15  Comp\n60:00  Hour')

    ok = True
    for name, cond in results:
        print(('PASS ' if cond else 'FAIL ') + name)
        ok = ok and cond
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0],
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('audio', nargs='?', metavar='AUDIO')
    ap.add_argument('--bot', metavar='NAME')
    ap.add_argument('--chat', metavar='ID')
    ap.add_argument('--title')
    ap.add_argument('--performer', default='Company Brief')
    ap.add_argument('--caption')
    ap.add_argument('--chapters', metavar='FILE')
    ap.add_argument('--allow-shared', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    if args.selftest:
        sys.exit(0 if selftest() else 1)

    if not args.audio or not args.bot:
        ap.error('AUDIO and --bot are required (unless --selftest)')

    token = None
    try:
        bots = load_bots()
        if args.bot not in bots:
            print(f'unknown bot "{args.bot}" (not in {BOTS_CONFIG})', file=sys.stderr)
            sys.exit(1)
        token = bots[args.bot]['token']
        chat_id = args.chat or bots[args.bot].get('default_chat_id')
        if not chat_id:
            print(f'no --chat given and no default_chat_id for bot "{args.bot}"', file=sys.stderr)
            sys.exit(1)

        if not os.path.isfile(args.audio):
            print(f'no such file: {args.audio}', file=sys.stderr)
            sys.exit(1)
        size = os.path.getsize(args.audio)
        if size > MAX_UPLOAD_BYTES:
            print(f'{args.audio} is {size} bytes, over the 50 MB Bot API upload limit -- '
                  f're-encode it smaller, e.g.: ffmpeg -i {args.audio} -b:a 64k out.mp3', file=sys.stderr)
            sys.exit(4)
        duration = get_duration_seconds(args.audio)

        # Chapters are loaded and fully validated BEFORE the gate/upload: a bad file must
        # refuse cleanly, not deliver the audio and then lose the chapters.
        title = args.title or os.path.splitext(os.path.basename(args.audio))[0]
        caption = truncate_caption(args.caption)
        chapters_path = resolve_chapters_path(args.audio, args.chapters)
        chapters_data = None
        if chapters_path:
            try:
                chapters_data = load_and_validate_chapters(chapters_path)
            except ChaptersError as e:
                print(f'refused: {e}', file=sys.stderr)
                sys.exit(5)

        try:
            owner_config = load_owner_config()
        except OwnerConfigError as e:
            print(f'refused: owner config invalid -- {e}', file=sys.stderr)
            sys.exit(3)
        if owner_config is None:
            print(f'warning: owner allowlist not configured ({OWNER_CONFIG}); '
                  f'applying membership-count/chat-type rule only')

        chat, member_count, admins, allowed, reason, rule = run_privacy_gate(
            token, chat_id, owner_config, args.allow_shared)
        if reason.startswith('WARNING'):
            print(reason)
        if not allowed:
            print(f'refused: chat type={chat.get("type")} title={chat.get("title")!r} '
                  f'members={member_count} -- {reason}', file=sys.stderr)
            sys.exit(3)

        identity = admin_identity_summary(chat, admins)

        if args.dry_run:
            print('DRY RUN -- nothing will be sent')
            print(f'  chat: type={chat.get("type")} title={chat.get("title")!r} '
                  f'members={member_count} id={chat_id}')
            print(f'  identity: {identity}  owner-rule: {rule}')
            print(f'  title: {title}')
            print(f'  performer: {args.performer}')
            print(f'  duration: {duration}s')
            print(f'  caption: {caption!r}')
            if chapters_data:
                print('  ' + format_chapters_message(chapters_data).replace('\n', '\n  '))
            return

        result = send_audio(token, chat_id, args.audio, title, args.performer, duration, caption)
        print(f'sent audio message_id={result["message_id"]} duration={duration}s size={size} bytes')

        if chapters_data:
            msg = api_call(token, 'sendMessage',
                            {'chat_id': chat_id, 'text': format_chapters_message(chapters_data)})
            print(f'sent chapters message_id={msg["message_id"]}')
    except DeliverError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(redact(f'ffprobe failed: {e}', token), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(redact(f'error: {e}', token), file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
