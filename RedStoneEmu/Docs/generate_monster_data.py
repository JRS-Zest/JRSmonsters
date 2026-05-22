#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_monster_data.py

C:\JRS\RED STONE\Data\Scenario\Red Stone\0548Map\ の全 JSON を集約し、
monster_viewer.html が読み込む monster_data.js を生成する。

使い方:
    python generate_monster_data.py
    → このスクリプトと同じフォルダに monster_data.js が出力される。
"""

import glob
import json
import math
import os
import sys
import csv
import struct

INPUT_DIR  = r'C:\JRS\RED STONE\Data\Scenario\Red Stone\0548Map'
OUTPUT_JS  = os.path.join(os.path.dirname(__file__), 'monster_data.js')
SAD_TABLE_CSV = os.path.normpath(os.path.join(
    os.path.dirname(__file__), '..', 'Tools', 'ghidra_scripts', 'sad_table_clean.csv'
))
VERIFIED_MAP_CSV = os.path.join(os.path.dirname(__file__), 'verified_monster_image_map.csv')
CREATURE_INFO_CSV = os.path.join(os.path.dirname(__file__), 'creatureInfo_creature.csv')
JOB2_DAT = r'C:\JRS\RED STONE\Data\Scenario\Red Stone\job2.dat'


def load_sad_table(path):
    """Load index->sad_name table dumped from Ghidra. Missing file is allowed."""
    table = {}
    if not os.path.exists(path):
        return table

    with open(path, encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                idx = int((row.get('index') or '').strip())
            except ValueError:
                continue
            name = (row.get('sad_name') or '').strip()
            if not name:
                continue
            table[idx] = name
    return table


def load_verified_map(path):
    """Load human-verified mapping: job2_index -> sad_name."""
    verified = {}
    if not os.path.exists(path):
        return verified

    with open(path, encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                bid = int((row.get('job2_index') or '').strip())
            except ValueError:
                continue
            sad = (row.get('sad_name') or '').strip()
            if not sad:
                continue
            verified[bid] = sad
    return verified


def _normalize_name(name):
    if not isinstance(name, str):
        return ''
    return ''.join(name.replace('\u3000', ' ').split()).lower()


def load_creature_name_map(path):
    """Load sokomin creature csv: monster name -> sad_name (graphic)."""
    name_map = {}
    if not os.path.exists(path):
        return name_map

    with open(path, encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get('name') or '').strip()
            sad = (row.get('graphic') or '').strip()
            if not name or not sad:
                continue
            name_map[name] = sad
            nk = _normalize_name(name)
            if nk and nk not in name_map:
                name_map[nk] = sad
    return name_map


def load_job2_effect_map(path):
    """Load Effect (uint32) from game-local job2.dat by job2 index."""
    effect_map = {}
    if not os.path.exists(path):
        sys.exit(f'ERROR: JRS job2.dat が見つかりません: {path}')

    with open(path, 'rb') as f:
        data = f.read()

    if len(data) < 12:
        return effect_map

    magic = struct.unpack_from('<I', data, 0)[0]
    if magic == 0x12345678:
        count = struct.unpack_from('<I', data, 8)[0]
        base = 12
    else:
        count = struct.unpack_from('<I', data, 0)[0]
        base = 4

    breed_size = 328
    effect_off = 4 + 32  # Index(4) + Name[32] -> Effect(uint32)
    for i in range(count):
        off = base + i * breed_size + effect_off
        if off + 4 > len(data):
            break
        effect_map[i] = struct.unpack_from('<I', data, off)[0]

    return effect_map


# ──────────────────────────────────────────────────────────────────────
#  集約処理
# ──────────────────────────────────────────────────────────────────────

def load_all(sad_table, verified_map, creature_name_map, effect_map):
    files = sorted(glob.glob(os.path.join(INPUT_DIR, '*.json')))
    if not files:
        sys.exit(f'ERROR: JSONが見つかりません: {INPUT_DIR}')

    maps    = []   # { id, name, file, breed_ids }
    breeds  = {}   # job2_index -> breed dict

    file_to_mid = {}  # map_file -> map id

    for f in files:
        with open(f, encoding='utf-8') as fp:
            d = json.load(fp)

        monsters = [r for r in d.get('records', [])
                    if r.get('char_type_name') == 'Monster']
        if not monsters:
            continue

        map_name = d.get('map_name') or os.path.basename(f)
        map_file = d.get('map_file', os.path.basename(f))

        # 同名マップが複数ファイルに分かれている場合は別エントリとして扱う
        mid = len(maps)
        file_to_mid[f] = mid
        maps.append({
            'id':   mid,
            'name': map_name,
            'file': map_file,
            'bids': [],   # breed_id list (重複なし)
        })

        for r in monsters:
            bid = r.get('job2_index', -1)
            if bid == -1:
                continue

            # ──── ブリード情報を登録（初回のみ）────
            if bid not in breeds:
                image_id = 100 + bid
                effect_id_raw = effect_map.get(bid)
                effect_id = (effect_id_raw & 0xFFFF) if isinstance(effect_id_raw, int) else None
                group_unknown_4 = r.get('group_unknown_4')
                group_imgsum_0 = r.get('group_imgsum_0')
                group_imgsum_1 = r.get('group_imgsum_1')
                group_imgsum_2 = r.get('group_imgsum_2')
                npc_name = (r.get('npc_name') or '').strip()
                breed_name = (r.get('breed_name') or '').strip()

                name_sad = None
                for candidate_name in (npc_name, breed_name):
                    if not candidate_name:
                        continue
                    name_sad = creature_name_map.get(candidate_name)
                    if not name_sad:
                        name_sad = creature_name_map.get(_normalize_name(candidate_name))
                    if name_sad:
                        break

                def sad_from_idx(v):
                    if isinstance(v, int) and v >= 0:
                        return sad_table.get(v)
                    return None

                sad_candidate_index = {
                    'job2_index': bid,
                    'image_id_server': image_id,
                    'image_id_minus_100': image_id - 100,
                    'image_id_minus_201': image_id - 201,
                    'effect_id': effect_id,
                    'effect_id_minus_201': (effect_id - 201) if isinstance(effect_id, int) else None,
                    'group_unknown_4': group_unknown_4,
                    'group_imgsum_0': group_imgsum_0,
                    'group_imgsum_1': group_imgsum_1,
                    'group_imgsum_2': group_imgsum_2,
                    'creature_name_match': None,
                }

                sad_candidates = {
                    # Hypothesis A: job2_index is same domain as sad table index.
                    'job2_index': sad_table.get(bid),
                    # Runtime image id variants.
                    'image_id_server': sad_table.get(image_id),
                    'image_id_minus_100': sad_table.get(image_id - 100),
                    'image_id_minus_201': sad_table.get(image_id - 201),
                    # Game-local job2.dat Breed.Effect domain.
                    'effect_id_minus_201': sad_table.get(effect_id - 201) if isinstance(effect_id, int) else None,
                    # MapActorGroup fields that are likely image-related.
                    'group_unknown_4': sad_from_idx(group_unknown_4),
                    'group_imgsum_0': sad_from_idx(group_imgsum_0),
                    'group_imgsum_1': sad_from_idx(group_imgsum_1),
                    'group_imgsum_2': sad_from_idx(group_imgsum_2),
                    # Fallback from public creature DB by monster name match.
                    'creature_name_match': name_sad,
                }

                di_raw = r.get('drop_items', '[]')
                di = json.loads(di_raw) if isinstance(di_raw, str) else (di_raw or [])
                valid_drops = [x for x in di if x.get('item_type', 65535) != 65535]

                sk_raw = r.get('skills', [])
                sk = json.loads(sk_raw) if isinstance(sk_raw, str) else (sk_raw or [])
                valid_skills = [s for s in sk if s not in (65535, -1)]

                breeds[bid] = {
                    'id':      bid,
                    'name':    r.get('npc_name') or r.get('breed_name') or '?',
                    'race':    r.get('race', ''),
                    'lineage': r.get('lineage', ''),
                    'sf':  r.get('status_factor', 0),
                    'lb':  r.get('level_up_bonus', 0),
                    'sb':  r.get('state_bonus', 0),
                    'dhp': r.get('default_hp', 0),
                    'dcp': r.get('default_cp', 0),
                    'str': r.get('STR', 0),
                    'agi': r.get('AGI', 0),
                    'con': r.get('CON', 0),
                    'wis': r.get('WIS', 0),
                    'int': r.get('INT', 0),
                    'cha': r.get('CHA', 0),
                    'lck': r.get('LCK', 0),
                    'atk_hi':  r.get('attack_max', 0),
                    'atk_lo':  r.get('attack_min', 0),
                    'bhi':     r.get('atk_bonus_max', 0),
                    'blo':     r.get('atk_bonus_min', 0),
                    'def':     r.get('defence', 0),
                    'db':      r.get('defence_bonus', 0),
                    'mag':     [
                        r.get('mag_fire', 0), r.get('mag_water', 0),
                        r.get('mag_wind', 0), r.get('mag_earth', 0),
                        r.get('mag_light', 0), r.get('mag_dark', 0),
                    ],
                    'abn': [
                        r.get('abn_darkness', 0), r.get('abn_poison', 0),
                        r.get('abn_sleep', 0),   r.get('abn_cold', 0),
                        r.get('abn_freeze', 0),  r.get('abn_stun', 0),
                        r.get('abn_petrify', 0), r.get('abn_confuse', 0),
                        r.get('abn_fascinate', 0),
                    ],
                    'all_abn':  r.get('all_abn_res', 0),
                    'all_dec':  r.get('all_decline', 0),
                    'all_sp':   r.get('all_spell', 0),
                    'fatal':    r.get('fatal_res', 0),
                    'dec':      r.get('decision_res', 0),
                    'move_spd': r.get('move_speed', 0),
                    'atk_spd':  r.get('attack_speed', 0),
                    'exp':      r.get('default_exp', 0),
                    'drops':    valid_drops,
                    'skills':   valid_skills,
                    'maps':     [],   # {mid, min, max, cnt}
                    # Keep multiple hypotheses until runtime validation decides which is correct.
                    'img': {
                        'image_id_server': image_id,
                        'effect_id': effect_id,
                        'group_unknown_4': group_unknown_4,
                        'group_imgsum': [group_imgsum_0, group_imgsum_1, group_imgsum_2],
                        'verified_sad': verified_map.get(bid),
                        'sad_candidate_index': sad_candidate_index,
                        'sad_candidates': sad_candidates,
                    },
                }

            # ──── マップ出現情報を追加 ────
            b = breeds[bid]
            existing = next((x for x in b['maps'] if x['mid'] == mid), None)
            pop = r.get('pop_speed', 0) or 0
            npc = r.get('npc_name') or ''
            if existing:
                existing['cnt'] += 1
                if pop > 0:
                    cur_min = existing['pop']
                    cur_max = existing.get('pop2', existing['pop'])
                    if cur_min > 0:
                        new_min = min(cur_min, pop)
                        new_max = max(cur_max, pop)
                        existing['pop'] = new_min
                        if new_max != new_min:
                            existing['pop2'] = new_max
                        elif 'pop2' in existing:
                            del existing['pop2']
                    else:
                        existing['pop'] = pop
                        existing.pop('pop2', None)
                # npc_nameが breed.name と異なる場合のみ保持（同マップ複数名は最初を使用）
                if 'npc' not in existing and npc and npc != b['name']:
                    existing['npc'] = npc
            else:
                entry = {
                    'mid': mid,
                    'min': r.get('min_level', 0),
                    'max': r.get('max_level', 0),
                    'cnt': 1,
                    'pop': pop,
                }
                if npc and npc != b['name']:
                    entry['npc'] = npc
                b['maps'].append(entry)
                if bid not in maps[mid]['bids']:
                    maps[mid]['bids'].append(bid)

    return maps, breeds


# ──────────────────────────────────────────────────────────────────────
#  JS 出力
# ──────────────────────────────────────────────────────────────────────

def main():
    print('読み込み中...')
    sad_table = load_sad_table(SAD_TABLE_CSV)
    verified_map = load_verified_map(VERIFIED_MAP_CSV)
    creature_name_map = load_creature_name_map(CREATURE_INFO_CSV)
    effect_map = load_job2_effect_map(JOB2_DAT)
    maps, breeds = load_all(sad_table, verified_map, creature_name_map, effect_map)

    breed_list = sorted(breeds.values(), key=lambda b: b['name'])

    data = {
        'maps':   maps,
        'breeds': breed_list,
        'image_map_meta': {
            'sad_table_csv': SAD_TABLE_CSV,
            'sad_table_count': len(sad_table),
            'verified_map_csv': VERIFIED_MAP_CSV,
            'verified_map_count': len(verified_map),
            'creature_info_csv': CREATURE_INFO_CSV,
            'creature_name_map_count': len(creature_name_map),
            'job2_dat': JOB2_DAT,
            'job2_effect_count': len(effect_map),
            'hypotheses': [
                'verified_only',
                'job2_index',
                'image_id_server',
                'image_id_minus_100',
                'image_id_minus_201',
                'effect_id_minus_201',
                'group_unknown_4',
                'group_imgsum_0',
                'group_imgsum_1',
                'group_imgsum_2',
                'creature_name_match',
            ],
        },
    }

    js_content = ('// Auto-generated by generate_monster_data.py\n'
                  'const MONSTER_DATA = '
                  + json.dumps(data, ensure_ascii=False, separators=(',', ':'))
                  + ';\n')

    with open(OUTPUT_JS, 'w', encoding='utf-8') as f:
        f.write(js_content)

    size_kb = os.path.getsize(OUTPUT_JS) // 1024
    print(f'生成完了: {OUTPUT_JS}')
    print(f'  マップ数: {len(maps)}')
    print(f'  ブリード数: {len(breed_list)}')
    print(f'  SADテーブル数: {len(sad_table)} ({SAD_TABLE_CSV})')
    print(f'  検証マップ数: {len(verified_map)} ({VERIFIED_MAP_CSV})')
    print(f'  job2 Effect数: {len(effect_map)} ({JOB2_DAT})')
    print(f'  ファイルサイズ: {size_kb} KB')


if __name__ == '__main__':
    main()
