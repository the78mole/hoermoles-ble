/**
 * Menu table lookups, driven by the real `shared/menu-tables.json` rather than
 * a fixture - the file is generated from `menu_settings.py`, so testing against
 * it also verifies the two stay compatible in shape.
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import {
  menuSettingForNumber,
  menuSettingForWireGroup,
  menuTableForProduct,
  menuTablesForProduct,
  parameterText,
  settingLabel,
  wireGroupForMenuNumber,
  type MenuTablesFile,
} from '../src/menu-tables.js';

const path = fileURLToPath(new URL('../../../../shared/menu-tables.json', import.meta.url));
const file: MenuTablesFile = JSON.parse(readFileSync(path, 'utf8'));

// The live-verified drive: Supramatic E4, the only table read-checked against
// real hardware.
const SUPRAMATIC_E4 = { productClass: 2, productId: 2 };

describe('product lookup', () => {
  it('finds the Supramatic E4 table', () => {
    const table = menuTableForProduct(file, SUPRAMATIC_E4.productClass, SUPRAMATIC_E4.productId);
    expect(table).not.toBeNull();
    expect(table!.product_name).toBe('Supramatic Serie 4');
    expect(table!.settings.length).toBeGreaterThan(50);
  });

  it('returns null for an unknown product', () => {
    expect(menuTableForProduct(file, 99, 99)).toBeNull();
    expect(menuTablesForProduct(file, 99, 99)).toEqual([]);
  });

  it('returns null when several firmware variants share a product id', () => {
    // SilentDrive 2 ships two tables distinguished only by software number, so
    // a caller has to disambiguate rather than get a silently wrong one.
    const ambiguous = file.tables
      .map((table) => menuTablesForProduct(file, table.product_class, table.product_id))
      .find((tables) => tables.length > 1);

    if (ambiguous) {
      const [first] = ambiguous;
      expect(menuTableForProduct(file, first.product_class, first.product_id)).toBeNull();
    }
  });
});

describe('setting lookup', () => {
  const table = menuTableForProduct(file, SUPRAMATIC_E4.productClass, SUPRAMATIC_E4.productId)!;

  it('maps menu number 1 (door type) to its wire group', () => {
    const setting = menuSettingForNumber(table, 1);
    expect(setting).not.toBeNull();
    expect(setting!.label).toBe('Torart');
    expect(wireGroupForMenuNumber(table, 1)).toBe(setting!.menu_group);
  });

  it('maps a wire group back to its setting', () => {
    const setting = menuSettingForNumber(table, 1)!;
    expect(menuSettingForWireGroup(table, setting.menu_group)?.menu_number).toBe(1);
  });

  it('returns null for unknown numbers and groups', () => {
    expect(menuSettingForNumber(table, 9999)).toBeNull();
    expect(menuSettingForWireGroup(table, 254)).toBeNull();
    expect(wireGroupForMenuNumber(table, 9999)).toBeNull();
  });

  it('prefers the English label where one was translated', () => {
    const setting = menuSettingForNumber(table, 1)!;
    expect(setting.label_en).toBe('Door type');
    expect(settingLabel(setting)).toBe('Door type');
  });

  it('falls back to the German label when no translation exists', () => {
    const untranslated = file.tables
      .flatMap((t) => t.settings)
      .find((setting) => setting.label_en === null);
    expect(untranslated).toBeDefined();
    expect(settingLabel(untranslated!)).toBe(untranslated!.label);
  });

  it('resolves a parameter value to its manufacturer text', () => {
    const setting = menuSettingForNumber(table, 1)!;
    expect(parameterText(setting, 0)).toBe('Sektionaltor');
    expect(parameterText(setting, 9999)).toBeNull();
  });

  it('marks one-shot processes as functional rather than stored values', () => {
    // Menu 10 is the learning run - writing to it starts a process, it does not
    // store a setting. The UI has to render those as actions.
    const learningRun = menuSettingForNumber(table, 10)!;
    expect(learningRun.is_functional).toBe(true);
    expect(menuSettingForNumber(table, 1)!.is_functional).toBe(false);
  });
});
