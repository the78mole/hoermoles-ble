import hoermoles_ble.menu_settings as ms


def test_drive_menu_tables_not_empty():
    assert len(ms.DRIVE_MENU_TABLES) == 8


def test_supramatic_e4_alias_matches_product_id_2_table():
    table = ms.menu_table_for_product(ms.SUPRAMATIC_E4_PRODUCT_CLASS, ms.SUPRAMATIC_E4_PRODUCT_ID)
    assert table is not None
    assert table.settings == ms.SUPRAMATIC_E4_MENU_TABLE


def test_menu_tables_for_product_single_match():
    tables = ms.menu_tables_for_product(2, 2)
    assert len(tables) == 1
    assert tables[0].product_name == "Supramatic Serie 4"


def test_menu_tables_for_product_unknown_returns_empty():
    assert ms.menu_tables_for_product(99, 99) == ()


def test_menu_tables_for_product_silentdrive2_has_two_firmware_variants():
    tables = ms.menu_tables_for_product(2, 33)
    assert len(tables) == 2
    assert {t.software_numbers for t in tables} == {("EE002449-00.aa",), ("EE002449-00.ai",)}


def test_menu_table_for_product_unambiguous():
    table = ms.menu_table_for_product(2, 17)
    assert table is not None
    assert table.product_name == "Rollmatic 2"


def test_menu_table_for_product_unknown_returns_none():
    assert ms.menu_table_for_product(99, 99) is None


def test_menu_table_for_product_ambiguous_without_software_number_returns_none():
    assert ms.menu_table_for_product(2, 33) is None


def test_menu_table_for_product_ambiguous_disambiguated_by_software_number():
    table = ms.menu_table_for_product(2, 33, software_number="EE002449-00.ai")
    assert table is not None
    assert table.software_numbers == ("EE002449-00.ai",)


def test_menu_table_for_product_ambiguous_with_non_matching_software_number_returns_none():
    assert ms.menu_table_for_product(2, 33, software_number="does-not-exist") is None


def test_menu_setting_for_number_found():
    setting = ms.menu_setting_for_number(ms.SUPRAMATIC_E4_MENU_TABLE, 101)
    assert setting is not None
    assert setting.menu_group == 101
    assert setting.label == "Antenne"


def test_menu_setting_for_number_not_found():
    assert ms.menu_setting_for_number(ms.SUPRAMATIC_E4_MENU_TABLE, 9999) is None


def test_menu_setting_for_wire_group_found():
    setting = ms.menu_setting_for_wire_group(ms.SUPRAMATIC_E4_MENU_TABLE, 60)
    assert setting is not None
    assert setting.menu_number == 99
    assert setting.label == "Reset"


def test_menu_setting_for_wire_group_not_found():
    assert ms.menu_setting_for_wire_group(ms.SUPRAMATIC_E4_MENU_TABLE, 9999) is None


def test_wire_group_for_menu_number_found():
    assert ms.wire_group_for_menu_number(ms.SUPRAMATIC_E4_MENU_TABLE, 101) == 101


def test_wire_group_for_menu_number_not_found():
    assert ms.wire_group_for_menu_number(ms.SUPRAMATIC_E4_MENU_TABLE, 9999) is None


def test_all_menu_numbers_unique_per_table():
    # menu_setting_for_number relies on menu_number being unique within a table
    for table in ms.DRIVE_MENU_TABLES:
        numbers = [s.menu_number for s in table.settings]
        assert len(numbers) == len(set(numbers)), f"duplicate menu_number in {table.product_name}"


def test_all_wire_groups_unique_per_table():
    for table in ms.DRIVE_MENU_TABLES:
        groups = [s.menu_group for s in table.settings]
        assert len(groups) == len(set(groups)), f"duplicate menu_group in {table.product_name}"


def test_reset_menu_is_functional_with_folgeablauf_default():
    setting = ms.menu_setting_for_number(ms.SUPRAMATIC_E4_MENU_TABLE, 97)
    assert setting.is_functional is True
    assert setting.parameters == (ms.MenuParameter(-1, "Folgeablauf", True),)
