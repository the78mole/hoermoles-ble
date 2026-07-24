/**
 * Types and lookups for `shared/menu-tables.json`, which is generated from
 * `hoermoles_ble.menu_settings` (see `hoermoles_ble.interop`). Do not hand-write
 * a second copy of these tables here - the generator plus its pytest guard is
 * what keeps the port and the reference implementation from drifting.
 *
 * The `menu_group` wire byte is specific to a (product_class, product_id)
 * combination, not a constant across products - looking a setting up under the
 * wrong table writes to the wrong parameter on a real drive.
 */

export interface MenuParameter {
  value: number;
  /** Manufacturer's original German, matching the printed manual and the
   * drive's own display - the authoritative wording to cross-check against. */
  text: string;
  is_default: boolean;
}

export interface MenuSetting {
  /** Human-facing Hoermann menu number (hand transmitter / display). */
  menu_number: number;
  /** Wire byte for GET_PROPERTIES/SET_PROPERTIES. */
  menu_group: number;
  label: string;
  label_en: string | null;
  /** True: triggers a one-shot process (a learning run, a reset) rather than
   * storing a value - the UI must present these as actions, not fields. */
  is_functional: boolean;
  parameters: MenuParameter[];
}

export interface DriveMenuTable {
  product_class: number;
  product_id: number;
  product_name: string;
  software_numbers: string[];
  settings: MenuSetting[];
}

export interface MenuTablesFile {
  _comment?: string;
  tables: DriveMenuTable[];
}

export function menuTablesForProduct(
  file: MenuTablesFile,
  productClass: number,
  productId: number,
): DriveMenuTable[] {
  return file.tables.filter(
    (table) => table.product_class === productClass && table.product_id === productId,
  );
}

/** The single table for a product, or null when there is none or when several
 * firmware variants exist and the caller has to disambiguate by software
 * number. */
export function menuTableForProduct(
  file: MenuTablesFile,
  productClass: number,
  productId: number,
): DriveMenuTable | null {
  const tables = menuTablesForProduct(file, productClass, productId);
  return tables.length === 1 ? tables[0] : null;
}

export function menuSettingForWireGroup(table: DriveMenuTable, menuGroup: number): MenuSetting | null {
  return table.settings.find((setting) => setting.menu_group === menuGroup) ?? null;
}

export function menuSettingForNumber(table: DriveMenuTable, menuNumber: number): MenuSetting | null {
  return table.settings.find((setting) => setting.menu_number === menuNumber) ?? null;
}

export function wireGroupForMenuNumber(table: DriveMenuTable, menuNumber: number): number | null {
  return menuSettingForNumber(table, menuNumber)?.menu_group ?? null;
}

/** Display label, preferring the English translation where one exists (so far
 * only the live-verified Supramatic E4 table has them). */
export function settingLabel(setting: MenuSetting): string {
  return setting.label_en ?? setting.label;
}

export function parameterText(setting: MenuSetting, value: number): string | null {
  return setting.parameters.find((parameter) => parameter.value === value)?.text ?? null;
}
