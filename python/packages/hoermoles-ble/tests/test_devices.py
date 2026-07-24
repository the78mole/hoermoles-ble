from hoermoles_ble.devices import (
    DeviceInfo,
    default_devices_registry_path,
    get_device_info,
    list_device_infos,
    load_device_registry,
    save_device_info,
)


def test_default_devices_registry_path(tmp_path):
    assert default_devices_registry_path(config_dir=tmp_path) == tmp_path / "devices.json"


def test_load_device_registry_empty_when_missing(tmp_path):
    assert load_device_registry(config_dir=tmp_path) == {}


def test_save_and_load_device_info_roundtrip(tmp_path):
    info = DeviceInfo(device_address="f1:26:af:cc:41:86", product_class=2, product_id=2, product_name="Supramatic E4")
    save_device_info(info, config_dir=tmp_path)

    registry = load_device_registry(config_dir=tmp_path)
    assert "F1:26:AF:CC:41:86" in registry
    loaded = registry["F1:26:AF:CC:41:86"]
    assert loaded.product_class == 2
    assert loaded.product_id == 2
    assert loaded.product_name == "Supramatic E4"
    assert loaded.updated_unix != 0


def test_save_device_info_upcases_address(tmp_path):
    info = DeviceInfo(device_address="aa:bb:cc:dd:ee:ff", product_class=1, product_id=1)
    save_device_info(info, config_dir=tmp_path)
    assert get_device_info("AA:BB:CC:DD:EE:FF", config_dir=tmp_path) is not None


def test_get_device_info_unknown_returns_none(tmp_path):
    assert get_device_info("00:00:00:00:00:00", config_dir=tmp_path) is None


def test_save_device_info_updates_existing_entry(tmp_path):
    save_device_info(DeviceInfo(device_address="AA:BB:CC:DD:EE:FF", product_class=1, product_id=1), config_dir=tmp_path)
    save_device_info(
        DeviceInfo(device_address="AA:BB:CC:DD:EE:FF", product_class=2, product_id=2, serial_no=12345),
        config_dir=tmp_path,
    )

    info = get_device_info("AA:BB:CC:DD:EE:FF", config_dir=tmp_path)
    assert info.product_class == 2
    assert info.serial_no == 12345
    assert len(load_device_registry(config_dir=tmp_path)) == 1


def test_list_device_infos_sorted_by_address(tmp_path):
    save_device_info(DeviceInfo(device_address="FF:FF:FF:FF:FF:FF", product_class=1, product_id=1), config_dir=tmp_path)
    save_device_info(DeviceInfo(device_address="AA:AA:AA:AA:AA:AA", product_class=1, product_id=1), config_dir=tmp_path)

    infos = list_device_infos(config_dir=tmp_path)
    assert [info.device_address for info in infos] == ["AA:AA:AA:AA:AA:AA", "FF:FF:FF:FF:FF:FF"]


def test_save_device_info_preserves_explicit_updated_unix(tmp_path):
    info = DeviceInfo(device_address="AA:BB:CC:DD:EE:FF", product_class=1, product_id=1, updated_unix=999)
    save_device_info(info, config_dir=tmp_path)
    loaded = get_device_info("AA:BB:CC:DD:EE:FF", config_dir=tmp_path)
    assert loaded.updated_unix == 999
