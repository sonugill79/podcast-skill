#!/usr/bin/env python3
"""Structural check of the plugin and marketplace manifests.

CI can't run `claude plugin validate --strict` (the CLI isn't installed there), so this checks the parts that
break installs: valid JSON, required fields, every userConfig option carrying title/type/description, and every
`source` path in the marketplace actually existing.
"""
import json, pathlib, sys

root = pathlib.Path(__file__).resolve().parent.parent
errors = []

mkt = json.loads((root / '.claude-plugin' / 'marketplace.json').read_text())
for field in ('name', 'owner', 'plugins'):
    if field not in mkt:
        errors.append(f'marketplace.json: missing {field}')
for entry in mkt.get('plugins', []):
    src = root / entry['source']
    if not (src / '.claude-plugin' / 'plugin.json').is_file():
        errors.append(f"marketplace.json: {entry['name']} -> {entry['source']} has no plugin.json")

for pj in root.glob('plugins/*/.claude-plugin/plugin.json'):
    man = json.loads(pj.read_text())
    for field in ('name', 'description', 'version'):
        if field not in man:
            errors.append(f'{pj}: missing {field}')
    for key, opt in man.get('userConfig', {}).items():
        for field in ('title', 'type', 'description'):
            if field not in opt:
                errors.append(f'{pj}: userConfig.{key} missing {field}')
        if 'enum' in opt:
            errors.append(f'{pj}: userConfig.{key} uses "enum", which the runtime rejects')
    skills = pj.parent.parent / 'skills'
    if not any(skills.glob('*/SKILL.md')):
        errors.append(f'{pj}: no skills/*/SKILL.md alongside the manifest')

print('\n'.join(f'FAIL {e}' for e in errors) if errors else 'manifests OK')
sys.exit(1 if errors else 0)
