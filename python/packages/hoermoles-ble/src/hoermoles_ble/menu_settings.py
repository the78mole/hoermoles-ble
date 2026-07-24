"""
"Menu concept" tables: map the classic numbered Hoermann hand-transmitter/
display menus (menu 20, menu 25, ...) to the wire-level byte ("menu group")
used by the GET_PROPERTIES/SET_PROPERTIES commands in protocol.py, plus the
valid parameter values per menu - for every drive product the official app
knows about, not just the Supramatic E4.

Source: the `menuconcept_*.json` embedded JSON resources of the decompiled
`Hoermann.App.Core.dll` (`Hoermann.App.Core.Menuconcept.DeviceSettingsManager`/
`DeviceSettings`), one file per (ProductClass, ProductID) - see DRIVE_MENU_TABLES
below for the full list. `DeviceClass = BitConverter.ToUInt16([ProductId,
ProductClass])`, i.e. ProductID distinguishes model variants *within* a
ProductClass (matches `hoermoles_ble.advertisement.PRODUCT_TYPE_NAMES`, which
is the source for the product_name strings below).

CORRECTION (found while cross-checking whether wire group 100 - see below -
also shows up for other products): earlier revisions of this module described
`menuconcept_sm4_01_ae.json` and `menuconcept_sm4_02_ai.json` as two firmware
revisions of the *same* Supramatic Serie 4 device. That was wrong - they are
two *different* ProductIDs (1 and 2) that merely share the same advertised
product_name ("Supramatic Serie 4"). Our live-tested device is ProductClass=2/
ProductID=2 (see F1:26:AF:CC:41:86 in the local reveng report) - that is the
`SUPRAMATIC_E4_MENU_TABLE` alias below. ProductID=1 is a distinct, structurally
similar but NOT interchangeable table (47 of 61 shared menu numbers have a
different menu_group wire byte) - do not use it for a ProductID=2 device or
vice versa. Only `menuconcept_sd2_00_aa.json`/`menuconcept_sd2_00_ai.json`
(SilentDrive 2) are genuinely two firmware revisions of the *same* ProductID
(33); DRIVE_MENU_TABLES keeps both as separate entries, disambiguated by
`software_numbers` (see menu_table_for_product()).

IMPORTANT - the menu_group wire byte is specific to each (product_class,
product_id[, firmware]) combination, not a fixed hardware constant across
products or even across ProductIDs of "the same" advertised product name.
Before calling HoermannClient.write_properties() against a real drive, read
back the current value for the target menu first (read_properties()) and
only write if there is no ambiguity - a wrong menu_group writes to the wrong
parameter.

LIVE VERIFICATION STATUS: only the Supramatic E4 table (ProductClass=2/
ProductID=2) has been read-verified against real hardware so far (see
protocol.py/client.py docstrings) - a full, unfiltered GET_PROPERTIES read
returned plausible values for every menu_group 1-99 and 101 in that table.
That same read also returned two additional wire groups NOT in ANY of the
tables below - 0 and 100 - presumably internal/reserved slots not exposed as
a named menu in the app for any product; harmless to ignore. All other
products' tables here are structurally derived from the decompiled resource
only, not yet verified against real hardware. The write direction
(SET_PROPERTIES) is not yet verified for any product.

Parameter `text` is kept in the manufacturer's original German (matches the
printed operator manual and the drive's own display) since that's the
authoritative reference to cross-check against. `label`/`label_en` on
MenuSetting give the (German original / unofficial English translation) menu
title for display purposes - `label_en` was only manually translated for the
live-verified Supramatic E4 table; every other product keeps `label_en=None`
(fall back to the German `label`) until someone actually needs that product
translated too.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

SUPRAMATIC_E4_PRODUCT_CLASS = 2
SUPRAMATIC_E4_PRODUCT_ID = 2


@dataclass(frozen=True)
class MenuParameter:
    value: int
    text: str
    is_default: bool


@dataclass(frozen=True)
class MenuSetting:
    menu_number: int   # human-facing Hoermann menu number (hand-transmitter/display menu)
    menu_group: int    # wire byte for GET_PROPERTIES/SET_PROPERTIES (protocol.py)
    label: str         # menu title, German (manufacturer original)
    label_en: Optional[str]  # menu title, unofficial English translation (only for
                             # Supramatic E4 so far - see module docstring)
    is_functional: bool  # True: triggers a sequential action ("Folgeablauf"/one-shot
                         # process like a learning run or reset), not a stored value -
                         # SET_PROPERTIES with any listed value just starts it
    parameters: Tuple[MenuParameter, ...]


@dataclass(frozen=True)
class DriveMenuTable:
    product_class: int
    product_id: int
    product_name: str  # matches hoermoles_ble.advertisement.PRODUCT_TYPE_NAMES
    software_numbers: Tuple[str, ...]  # "EE......-NN.xx" entries this table applies to -
                                       # compare against a device's own GET_SOFTWARE_VERSION
                                       # to disambiguate when menu_tables_for_product()
                                       # returns more than one table (see SilentDrive 2 below)
    settings: Tuple[MenuSetting, ...]


# --- Supramatic Serie 4, ProductID=2 ("Supramatic E4") ----------------------
# Source: menuconcept_sm4_02_ai.json. Live read-verified (F1:26:AF:CC:41:86).
_SM4_PRODUCT_ID_2_SETTINGS: Tuple[MenuSetting, ...] = (
    MenuSetting(1, 1, 'Torart', 'Door type', False, (MenuParameter(0, 'Sektionaltor', True), MenuParameter(1, 'Schwingtor', False), MenuParameter(2, 'Seiten-Sektionaltor', False), MenuParameter(3, 'Kipptor', False), MenuParameter(4, 'Decken-Gliedertor', False), MenuParameter(5, 'Canopy Tor', False))),
    MenuSetting(10, 2, 'Lernfahrten', 'Learning runs', True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(11, 3, 'Funk lernen: Impuls', 'Radio teach-in: Impulse', True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(12, 4, 'Funk lernen: Antriebsbeleuchtung', 'Radio teach-in: Operator light', True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(13, 5, 'Funk lernen: Teil-Öffnung', 'Radio teach-in: Partial opening', True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(14, 6, 'Funk lernen: Tor-Auf', 'Radio teach-in: Door open', True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(15, 7, 'Funk lernen: Tor-Zu', 'Radio teach-in: Door close', True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(16, 8, 'Funk lernen: Lüftungsposition', 'Radio teach-in: Ventilation position', True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(17, 9, 'Alle Funkcodes lernen (Gateway)', 'Learn all radio codes (gateway)', True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(18, 10, 'WLAN', 'WiFi', False, (MenuParameter(0, 'Deaktivieren', True), MenuParameter(1, 'Aktivieren', False))),
    MenuSetting(19, 11, 'Funk löschen', 'Delete radio codes', False, (MenuParameter(0, 'Zurück', True), MenuParameter(1, 'Funk', False), MenuParameter(2, 'BLE', False), MenuParameter(3, 'WLAN', False), MenuParameter(4, 'Alle', False))),
    MenuSetting(20, 12, 'Reversiergrenze einstellen', 'Set reversal limit', True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(21, 13, 'Überwachung Schlupftürkontakt', 'Wicket door contact monitoring', False, (MenuParameter(0, 'Schlupftürkontakt deaktiviert ( oder ohne Testung)', True), MenuParameter(1, 'Schlupftürkontakt mit Testung', False))),
    MenuSetting(22, 14, 'Gurtentlastung Tor-Zu', 'Belt relief, Close direction', False, (MenuParameter(0, 'ohne', False), MenuParameter(1, 'Kurz', True), MenuParameter(2, 'Mittel', False), MenuParameter(3, 'Lang', False))),
    MenuSetting(23, 15, 'Position ändern', 'Change position', False, (MenuParameter(0, 'Zurück', True), MenuParameter(1, 'Position Teilöffnung ändern', False), MenuParameter(2, 'Position Lüften ändern', False))),
    MenuSetting(25, 16, 'Beleuchtung Intern deaktiviert', 'Internal lighting deactivated', False, (MenuParameter(0, 'Menu deaktiv', False), MenuParameter(1, 'Menu aktiv', True))),
    MenuSetting(26, 17, 'Nachleuchtdauer Intern (durch Antrieb)', 'Afterglow duration, internal (by operator)', False, (MenuParameter(0, 'Deaktiviert', False), MenuParameter(1, '30 Sek.', False), MenuParameter(2, '60 Sek.', False), MenuParameter(3, '120 Sek.', True), MenuParameter(4, '180 Sek.', False), MenuParameter(5, '300 Sek.', False), MenuParameter(6, '600 Sek.', False))),
    MenuSetting(27, 18, 'Nachleuchtdauer Externe Beleuchtung', 'Afterglow duration, external light', False, (MenuParameter(0, 'Deaktiviert', False), MenuParameter(1, '30 Sek.', False), MenuParameter(2, '60 Sek.', False), MenuParameter(3, '180 Sek.', False), MenuParameter(4, '300 Sek.', True), MenuParameter(5, '600 Sek.', False))),
    MenuSetting(28, 19, "Dauer 'EIN'-Funktion externe Beleuchtung über HOR1 oder 3. Relais UAP1 (Schaltbar über Funk bzw. Taster)", "Duration of the external light 'ON' function via HOR1 or 3rd relay UAP1 (switchable via radio or button)", False, (MenuParameter(0, 'deaktiviert', True), MenuParameter(1, 'aktiviert', False))),
    MenuSetting(29, 20, 'Lauflicht', 'Chase light', False, (MenuParameter(0, 'Deaktiviert', True), MenuParameter(1, 'Aktiviert bei Torfahrt', False), MenuParameter(2, 'Aktiviert bei Anfahr-/ Vorwarnung', False), MenuParameter(3, 'Aktiviert bei Torfahrt und Anfahr-/ Vorwarnung', False), MenuParameter(4, 'Aktiviert bei Torfahrt (Laufrichtung invertiert)', False), MenuParameter(5, 'Aktiviert bei Anfahr-/ Vorwarnung (Laufrichtung invertiert)', False), MenuParameter(6, 'Aktiviert bei Torfahrt und Anfahr-/ Vorwarnung (Laufrichtung invertiert)', False))),
    MenuSetting(30, 21, 'Relasifunktionen Extern HCP HOR1/3 oder UAP1', 'External relay functions HCP HOR1/3 or UAP1', False, (MenuParameter(0, 'Externes Relais deaktiviert', False), MenuParameter(1, 'Funktion Beleuchtung extern', True), MenuParameter(2, "Meldung 'Endlage Tor Auf'", False), MenuParameter(3, "Meldung 'Endlage Tor Zu'", False), MenuParameter(4, "Meldung 'Endlage Teilöffnung'", False), MenuParameter(5, 'Wischsignal bei Befehlsgabe', False), MenuParameter(6, 'Meldung Fehlermeldung auf dem Display (Störung)', False), MenuParameter(7, 'Anfahr-/Vor-/Fahrwarnung Dauersignal', False), MenuParameter(8, 'Anfahr-/Vor-/Fahrwarnung blinkend', False), MenuParameter(9, 'Relais zieht während der Fahrt an', False), MenuParameter(10, 'Meldung Inspektion bei Anzeige in', False), MenuParameter(11, 'Wie interne Beleuchtung/Nachleuchtdauer', False))),
    MenuSetting(32, 22, 'Vorwarnzeit', 'Pre-warning time', False, (MenuParameter(0, 'Deaktiviert', True), MenuParameter(1, '1 Sek.', False), MenuParameter(2, '2 Sek.', False), MenuParameter(3, '3 Sek.', False), MenuParameter(4, '4 Sek.', False), MenuParameter(5, '5 Sek.', False), MenuParameter(6, '10 Sek.', False), MenuParameter(7, '15 Sek.', False), MenuParameter(8, '20 Sek.', False), MenuParameter(9, '30 Sek.', False), MenuParameter(10, '60 Sek.', False))),
    MenuSetting(33, 23, 'Vorwarnrichtung', 'Advance warning direction', False, (MenuParameter(0, 'Vorwarnen in Richtung Zu', True), MenuParameter(1, 'Vorwarnen in Richtung Auf und Zu', False))),
    MenuSetting(34, 24, 'Automatischer Zulauf - Aufhaltezeit', 'Automatic closing - hold-open time', False, (MenuParameter(0, 'Deaktiviert', True), MenuParameter(1, '5 Sek.', False), MenuParameter(2, '10 Sek.', False), MenuParameter(3, '15 Sek.', False), MenuParameter(4, '30 Sek.', False), MenuParameter(5, '60 Sek.', False), MenuParameter(6, '90 Sek.', False), MenuParameter(7, '120 Sek.', False), MenuParameter(8, '180 Sek.', False), MenuParameter(9, '240 Sek.', False), MenuParameter(10, '300 Sek.', False))),
    MenuSetting(35, 25, 'Automatischer Zulauf - Aufhaltezeit in Teilöffnung', 'Automatic closing - hold-open time in partial opening', False, (MenuParameter(0, 'Deaktiviert', True), MenuParameter(1, 'wie Menü 34', False), MenuParameter(2, '15 Sek.', False), MenuParameter(3, '30 Sek.', False), MenuParameter(4, '15 Min.', False), MenuParameter(5, '30 Min.', False), MenuParameter(6, '60 Min.', False), MenuParameter(7, '90 Min.', False), MenuParameter(8, '120 Min.', False), MenuParameter(9, '180 Min.', False), MenuParameter(10, '240 Min.', False))),
    MenuSetting(36, 26, 'Bedientasten am Antrieb', 'Control buttons on the operator', False, (MenuParameter(0, 'Deaktiviert', False), MenuParameter(1, 'Aktiviert', True))),
    MenuSetting(37, 27, 'Reset', 'Reset', False, (MenuParameter(0, 'Zurück', True), MenuParameter(1, 'Reset/Bus Scan HCP2 Bus', False), MenuParameter(2, 'Reset Parameter ab 20 - 36', False), MenuParameter(3, 'Werksreset', False))),
    MenuSetting(38, 28, 'Erweiterte Menüs freigeschaltet', 'Extended menus unlocked', False, (MenuParameter(0, 'Platzhalter', True),)),
    MenuSetting(39, 29, 'Impulsverhalten', 'Impulse behavior', False, (MenuParameter(0, 'Impuls verlängert die Aufhaltezeit (mit allen Befehlsgeräten außer Tor Zu)', True), MenuParameter(1, 'Impuls bricht die Aufhaltezeit ab ( mit allen Befehlsgeräten außer Tor Auf)', False))),
    MenuSetting(40, 30, 'Betriebsart', 'Operating mode', False, (MenuParameter(1, 'Impulsfolge', True), MenuParameter(2, 'Impulsfolge nur in der Endlage', False), MenuParameter(3, 'sofortige Richtungsumkehr bei Richtungsbefehl', False))),
    MenuSetting(41, 31, 'Sicherheitseinrichtung SE1', 'Safety device SE1', False, (MenuParameter(0, 'deaktiviert', True), MenuParameter(1, '2-Draht LS statisch / dynamisch', False))),
    MenuSetting(42, 32, 'Sicherheitseinrichtung SE1 Funktion', 'Safety device SE1 function', False, (MenuParameter(0, 'Wirkrichtung Tor-Zu kurzes Reversieren', False), MenuParameter(1, 'Wirkrichtung Tor-Zu langes Reversieren', True), MenuParameter(2, 'Wirkrichtung Tor-Zu entlasten', False), MenuParameter(3, 'Wirkrichtung Tor-Auf kurzes Reversieren', False), MenuParameter(4, 'Wirkrichtung Tor-Auf langes Reversieren', False), MenuParameter(5, 'Wirkrichtung Tor-Auf entlasten', False), MenuParameter(6, 'Wirkrichtung Tor-Zu und Tor-Auf kurzes Reversieren', False))),
    MenuSetting(43, 33, 'Sicherheitseinrichtung SE2', 'Safety device SE2', False, (MenuParameter(0, 'deaktiviert', True), MenuParameter(1, 'SKS', False), MenuParameter(2, 'VL', False), MenuParameter(3, 'Funk-SKS', False), MenuParameter(4, '8k2', False))),
    MenuSetting(44, 34, 'Sicherheitseinrichtung SE2 Funktion', 'Safety device SE2 function', False, (MenuParameter(0, 'Wirkrichtung Tor-Zu kurzes Reversieren', False), MenuParameter(1, 'Wirkrichtung Tor-Zu langes Reversieren', True), MenuParameter(2, 'Wirkrichtung Tor-Zu entlasten', False), MenuParameter(3, 'Wirkrichtung Tor-Auf kurzes Reversieren', False), MenuParameter(4, 'Wirkrichtung Tor-Auf langes Reversieren', False), MenuParameter(5, 'Wirkrichtung Tor-Auf entlasten', False), MenuParameter(6, 'Wirkrichtung Tor-Zu und Tor-Auf kurzes Reversieren', False))),
    MenuSetting(48, 35, 'Verhalten bei Ansprechen der Kraftbegrenzung in Wirkrichtung Auf', 'Behavior when the force limit responds, Open direction', False, (MenuParameter(0, 'Entlasten', True), MenuParameter(1, 'Kurzes Reversieren', False), MenuParameter(2, 'Langes Reversieren', False))),
    MenuSetting(49, 36, 'Verhalten bei Ansprechen der Kraftbegrenzung in Wirkrichtung Zu', 'Behavior when the force limit responds, Close direction', False, (MenuParameter(0, 'Entlasten', False), MenuParameter(1, 'Kurzes Reversieren', True), MenuParameter(2, 'Langes Reversieren', False))),
    MenuSetting(50, 37, 'Kraftbegrenzung Tor-Auf', 'Force limit, door open', False, (MenuParameter(0, 'Stufe 0', False), MenuParameter(1, 'Stufe 1', False), MenuParameter(2, 'Stufe 2', False), MenuParameter(3, 'Stufe 3', False), MenuParameter(4, 'Stufe 4', True), MenuParameter(5, 'Stufe 5', False), MenuParameter(6, 'Stufe 6', False), MenuParameter(7, 'Stufe 7', False), MenuParameter(8, 'Stufe 8', False), MenuParameter(9, 'Stufe 9', False), MenuParameter(10, 'Stufe 10', False))),
    MenuSetting(51, 38, 'Kraftbegrenzung Tor-Zu', 'Force limit, door close', False, (MenuParameter(0, 'Stufe 0', False), MenuParameter(1, 'Stufe 1', False), MenuParameter(2, 'Stufe 2', False), MenuParameter(3, 'Stufe 3', False), MenuParameter(4, 'Stufe 4', True), MenuParameter(5, 'Stufe 5', False), MenuParameter(6, 'Stufe 6', False), MenuParameter(7, 'Stufe 7', False), MenuParameter(8, 'Stufe 8', False), MenuParameter(9, 'Stufe 9', False), MenuParameter(10, 'Stufe 10', False))),
    MenuSetting(52, 39, 'Geschwindigkeit Tor-Auf', 'Speed, door open', False, (MenuParameter(0, 'Sehr schnell', True), MenuParameter(1, 'Schnell', False), MenuParameter(2, 'Mittel', False), MenuParameter(3, 'Langsam', False))),
    MenuSetting(53, 40, 'Geschwindigkeit Tor-Zu', 'Speed, door close', False, (MenuParameter(0, 'Sehr schnell', False), MenuParameter(1, 'Schnell', False), MenuParameter(2, 'Mittel', False), MenuParameter(3, 'Langsam', True))),
    MenuSetting(54, 41, 'Schleichfahrtgeschwindigkeit Tor-Auf', 'Creep speed, door open', False, (MenuParameter(0, 'Maximal', False), MenuParameter(1, 'Mittel', True), MenuParameter(2, 'Langsam', False))),
    MenuSetting(55, 42, 'Schleichfahrtgeschwindigkeit Tor-Zu', 'Creep speed, door close', False, (MenuParameter(0, 'Maximal', False), MenuParameter(1, 'Mittel', True), MenuParameter(2, 'Langsam', False))),
    MenuSetting(56, 43, 'Startpunkte Schleichfahrt Tor-Auf', 'Start points, creep speed door open', False, (MenuParameter(0, 'Kurz', False), MenuParameter(1, 'Mittel', True), MenuParameter(2, 'Lang', False))),
    MenuSetting(57, 44, 'Startpunkte Schleichfahrt Tor-Zu', 'Start points, creep speed door close', False, (MenuParameter(0, 'Kurz', False), MenuParameter(1, 'Mittel', True), MenuParameter(2, 'Lang', False))),
    MenuSetting(58, 45, 'Sondertortyp', 'Special door type', False, (MenuParameter(0, 'Nicht gesetzt', True), MenuParameter(1, 'Gesetzt', False))),
    MenuSetting(59, 46, 'Gurtentlastung Tor-Auf', 'Belt relief, door open', False, (MenuParameter(0, 'Ohne', False), MenuParameter(1, 'Kurz', False), MenuParameter(2, 'Mittel', True), MenuParameter(3, 'Lang', False))),
    MenuSetting(61, 47, 'Position ändern', 'Change position', False, (MenuParameter(0, 'Position Lüften default', True), MenuParameter(1, 'Position ändern', False))),
    MenuSetting(66, 48, 'Max. Lernkräfte', 'Max. learning forces', False, (MenuParameter(0, 'Stufe 0', True), MenuParameter(1, 'Stufe 1', False), MenuParameter(2, 'Stufe 2', False))),
    MenuSetting(88, 49, 'Anzeige Antriebstyp und Ausführung (Menu 1-9)', 'Display operator type and version (menu 1-9)', True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(89, 50, 'Wartungsanzeige', 'Maintenance indicator', False, (MenuParameter(0, 'deaktiviert', True), MenuParameter(1, '1.000', False), MenuParameter(2, '2.000', False), MenuParameter(3, '3.000', False), MenuParameter(4, '4.000', False), MenuParameter(5, '5.000', False), MenuParameter(6, '7.500', False), MenuParameter(7, '10.000', False), MenuParameter(8, '180 Tage', False), MenuParameter(9, '360 Tage', False))),
    MenuSetting(90, 51, 'Zähler Wartungsanzeige zurück setzen', 'Reset maintenance indicator counter', True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(91, 52, 'Letzte 10 Fehlermeldungen auslesen', 'Read out the last 10 error messages', True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(92, 53, 'Position letzter Kraftfehler anfahren', 'Move to position of last force error', True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(93, 54, 'Fehlerspeicher zurücksetzen/löschen', 'Reset/clear error memory', True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(94, 55, 'Torzyklen unvollständig auslesen', 'Read out incomplete door cycles', True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(95, 56, 'Betriebsstunden gesamt auslesen', 'Read out total operating hours', True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(96, 57, 'Reversiergrenzen zurücksetzen', 'Reset reversal limits', True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(97, 58, 'Betriebskräfte zurücksetzen', 'Reset operating forces', True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(98, 59, 'Einstellungen Schleichfahrten zurücksetzen', 'Reset creep speed settings', True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(99, 60, 'Reset', 'Reset', True, (MenuParameter(0, 'Zurück', True), MenuParameter(1, 'Reset/Bus Scan HCP2 Bus', False), MenuParameter(2, 'Reset Parameter ab 20-36', False), MenuParameter(3, 'Reset Parameter ab 38-96 (90-95 nicht)', False), MenuParameter(4, 'Werksreset', False))),
    MenuSetting(101, 101, 'Antenne', 'Antenna', False, (MenuParameter(0, 'Interne Antenne', True), MenuParameter(1, 'Externe Antenne', False))),
)

# --- Supramatic Serie 4, ProductID=1 - a DIFFERENT product from the E4 above,
# not a firmware revision of it (see module docstring). Source: menuconcept_sm4_01_ae.json.
_SM4_PRODUCT_ID_1_SETTINGS: Tuple[MenuSetting, ...] = (
    MenuSetting(1, 1, 'Torart', None, False, (MenuParameter(0, 'Sektionaltor', True), MenuParameter(1, 'Schwingtor', False), MenuParameter(2, 'Seiten-Sektionaltor', False), MenuParameter(3, 'Kipptor', False), MenuParameter(4, 'Decken-Gliedertor', False))),
    MenuSetting(10, 2, 'Lernfahrten', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(11, 3, 'Funk lernen: Impuls', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(12, 4, 'Funk lernen: Antriebsbeleuchtung', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(13, 5, 'Funk lernen: Teil-Öffnung', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(14, 6, 'Funk lernen: Tor-Auf', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(15, 7, 'Funk lernen: Tor-Zu', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(16, 8, 'Alle Funkcodes lernen (Gateway)', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(18, 9, 'WLAN', None, False, (MenuParameter(0, 'Deaktivieren', True), MenuParameter(1, 'Aktivieren', False))),
    MenuSetting(19, 10, 'Funk löschen', None, False, (MenuParameter(0, 'Zurück', True), MenuParameter(1, 'Funk', True), MenuParameter(2, 'BLE', False), MenuParameter(3, 'WLAN', False), MenuParameter(4, 'Alle', False))),
    MenuSetting(23, 11, 'Position ändern', None, False, (MenuParameter(0, 'Zurück', True), MenuParameter(1, 'Position Teilöffnung ändern', False), MenuParameter(2, 'Position Lüften ändern', False))),
    MenuSetting(25, 12, 'Beleuchtung Intern deaktiviert', None, False, (MenuParameter(0, 'Menu deaktiv', False), MenuParameter(1, 'Menu aktiv', True))),
    MenuSetting(26, 13, 'Nachleuchtdauer Intern (durch Antrieb)', None, False, (MenuParameter(0, 'Deaktiviert', False), MenuParameter(1, '30 Sek.', False), MenuParameter(2, '60 Sek.', False), MenuParameter(3, '120 Sek.', True), MenuParameter(4, '180 Sek.', False), MenuParameter(5, '300 Sek.', False), MenuParameter(6, '600 Sek.', False))),
    MenuSetting(27, 14, 'Nachleuchtdauer Externe Beleuchtung', None, False, (MenuParameter(0, 'Deaktiviert', False), MenuParameter(1, '30 Sek.', False), MenuParameter(2, '60 Sek.', False), MenuParameter(3, '180 Sek.', False), MenuParameter(4, '300 Sek.', True), MenuParameter(5, '600 Sek.', False))),
    MenuSetting(28, 15, "Dauer 'EIN'-Funktion externe Beleuchtung über HOR1 oder 3. Relais UAP1 (Schaltbar über Funk bzw. Taster)", None, False, (MenuParameter(0, 'deaktiviert', True), MenuParameter(1, 'aktiviert', False))),
    MenuSetting(29, 16, 'Lauflicht', None, False, (MenuParameter(0, 'Deaktiviert', True), MenuParameter(1, 'Aktiviert bei Torfahrt', False), MenuParameter(2, 'Aktiviert bei Anfahr-/ Vorwarnung', False), MenuParameter(3, 'Aktiviert bei Torfahrt und Anfahr-/ Vorwarnung', False))),
    MenuSetting(30, 17, 'Relasifunktionen Extern HCP HOR1/3 oder UAP1', None, False, (MenuParameter(0, 'Externes Relais deaktiviert', False), MenuParameter(1, 'Funktion Beleuchtung extern', True), MenuParameter(2, "Meldung 'Endlage Tor Auf'", False), MenuParameter(3, "Meldung 'Endlage Tor Zu'", False), MenuParameter(4, "Meldung 'Endlage Teilöffnung'", False), MenuParameter(5, 'Wischsignal bei Befehlsgabe', False), MenuParameter(6, 'Meldung Fehlermeldung auf dem Display (Störung)', False), MenuParameter(7, 'Anfahr-/Vor-/Fahrwarnung Dauersignal', False), MenuParameter(8, 'Anfahr-/Vor-/Fahrwarnung blinkend', False), MenuParameter(9, 'Relais zieht während der Fahrt an', False), MenuParameter(10, 'Meldung Inspektion bei Anzeige in', False), MenuParameter(11, 'Wie interne Beleuchtung/Nachleuchtdauer', False))),
    MenuSetting(32, 18, 'Vorwarnzeit', None, False, (MenuParameter(0, 'Deaktiviert', True), MenuParameter(1, '1 Sek.', False), MenuParameter(2, '2 Sek.', False), MenuParameter(3, '3 Sek.', False), MenuParameter(4, '4 Sek.', False), MenuParameter(5, '5 Sek.', False), MenuParameter(6, '10 Sek.', False), MenuParameter(7, '15 Sek.', False), MenuParameter(8, '20 Sek.', False), MenuParameter(9, '30 Sek.', False), MenuParameter(10, '60 Sek.', False))),
    MenuSetting(33, 19, 'Vorwarnrichtung', None, False, (MenuParameter(0, 'Vorwarnen in Richtung Zu', True), MenuParameter(1, 'Vorwarnen in Richtung Auf und Zu', False))),
    MenuSetting(34, 20, 'Automatischer Zulauf - Aufhaltezeit', None, False, (MenuParameter(0, 'Deaktiviert', True), MenuParameter(1, '5 Sek.', False), MenuParameter(2, '10 Sek.', False), MenuParameter(3, '15 Sek.', False), MenuParameter(4, '30 Sek.', False), MenuParameter(5, '60 Sek.', False), MenuParameter(6, '90 Sek.', False), MenuParameter(7, '120 Sek.', False), MenuParameter(8, '180 Sek.', False), MenuParameter(9, '240 Sek.', False), MenuParameter(10, '300 Sek.', False))),
    MenuSetting(35, 21, 'Automatischer Zulauf - Aufhaltezeit in Teilöffnung', None, False, (MenuParameter(0, 'Deaktiviert', True), MenuParameter(1, 'wie Menü 34', False), MenuParameter(2, '15 Sek.', False), MenuParameter(3, '30 Sek.', False), MenuParameter(4, '15 Min.', False), MenuParameter(5, '30 Min.', False), MenuParameter(6, '60 Min.', False), MenuParameter(7, '90 Min.', False), MenuParameter(8, '120 Min.', False), MenuParameter(9, '180 Min.', False), MenuParameter(10, '240 Min.', False))),
    MenuSetting(36, 22, 'Bedientasten am Antrieb', None, False, (MenuParameter(0, 'Deaktiviert', False), MenuParameter(1, 'Aktiviert', True))),
    MenuSetting(37, 23, 'Reset', None, False, (MenuParameter(0, 'Zurück', True), MenuParameter(1, 'Reset/Bus Scan HCP2 Bus', False), MenuParameter(2, 'Reset Parameter ab 20 - 36', False), MenuParameter(3, 'Werksreset', False))),
    MenuSetting(38, 24, 'Erweiterte Menüs freigeschaltet', None, False, (MenuParameter(0, 'Platzhalter', True),)),
    MenuSetting(39, 25, 'Impulsverhalten', None, False, (MenuParameter(0, 'Impuls verlängert die Aufhaltezeit (mit allen Befehlsgeräten außer Tor Zu)', True), MenuParameter(1, 'Impuls bricht die Aufhaltezeit ab ( mit allen Befehlsgeräten außer Tor Auf)', False))),
    MenuSetting(40, 26, 'Betriebsart', None, False, (MenuParameter(1, 'Impulsfolge', True), MenuParameter(2, 'Impulsfolge nur in der Endlage', False), MenuParameter(3, 'sofortige Richtungsumkehr bei Richtungsbefehl', False))),
    MenuSetting(41, 27, 'Sicherheitseinrichtung SE1', None, False, (MenuParameter(0, 'deaktiviert', True), MenuParameter(1, '2-Draht LS statisch / dynamisch', False), MenuParameter(2, '3-Draht LS / statisch Getestet', False), MenuParameter(3, '3-Draht LS / statisch ungetestet', False), MenuParameter(4, '8k2', False))),
    MenuSetting(42, 28, 'Sicherheitseinrichtung SE1 Funktion', None, False, (MenuParameter(0, 'Wirkrichtung Tor-Zu kurzes Reversieren', False), MenuParameter(1, 'Wirkrichtung Tor-Zu langes Reversieren', True), MenuParameter(2, 'Wirkrichtung Tor-Zu entlasten', False), MenuParameter(3, 'Wirkrichtung Tor-Auf kurzes Reversieren', False), MenuParameter(4, 'Wirkrichtung Tor-Auf langes Reversieren', False), MenuParameter(5, 'Wirkrichtung Tor-Auf entlasten', False), MenuParameter(6, 'Wirkrichtung Tor-Zu und Tor-Auf kurzes Reversieren', False))),
    MenuSetting(43, 29, 'Sicherheitseinrichtung SE2', None, False, (MenuParameter(0, 'deaktiviert', True), MenuParameter(1, 'SKS', False), MenuParameter(2, 'VL', False), MenuParameter(3, 'Funk-SKS', False), MenuParameter(4, '8k2', False), MenuParameter(5, '3-Draht LS / statisch Getestet', False), MenuParameter(6, '3-Draht LS / statisch ungetestet', False))),
    MenuSetting(44, 30, 'Sicherheitseinrichtung SE2 Funktion', None, False, (MenuParameter(0, 'Wirkrichtung Tor-Zu kurzes Reversieren', False), MenuParameter(1, 'Wirkrichtung Tor-Zu langes Reversieren', True), MenuParameter(2, 'Wirkrichtung Tor-Zu entlasten', False), MenuParameter(3, 'Wirkrichtung Tor-Auf kurzes Reversieren', False), MenuParameter(4, 'Wirkrichtung Tor-Auf langes Reversieren', False), MenuParameter(5, 'Wirkrichtung Tor-Auf entlasten', False), MenuParameter(6, 'Wirkrichtung Tor-Zu und Tor-Auf kurzes Reversieren', False))),
    MenuSetting(47, 31, 'Überwachung Schlupftürkontakt', None, False, (MenuParameter(0, 'Schlupftürkontakt deaktiviert (oder ohne Testung)', True), MenuParameter(1, 'Schlupftürkontakt mit Testung', False))),
    MenuSetting(48, 32, 'Verhalten bei Ansprechen der Kraftbegrenzung in Wirkrichtung Auf', None, False, (MenuParameter(0, 'Entlasten', True), MenuParameter(1, 'Kurzes Reversieren', False), MenuParameter(2, 'Langes Reversieren', False))),
    MenuSetting(49, 33, 'Verhalten bei Ansprechen der Kraftbegrenzung in Wirkrichtung Zu', None, False, (MenuParameter(0, 'Entlasten', False), MenuParameter(1, 'Kurzes Reversieren', True), MenuParameter(2, 'Langes Reversieren', False))),
    MenuSetting(50, 34, 'Kraftbegrenzung Tor-Auf', None, False, (MenuParameter(0, 'Stufe 0', False), MenuParameter(1, 'Stufe 1', False), MenuParameter(2, 'Stufe 2', False), MenuParameter(3, 'Stufe 3', False), MenuParameter(4, 'Stufe 4', True), MenuParameter(5, 'Stufe 5', False), MenuParameter(6, 'Stufe 6', False), MenuParameter(7, 'Stufe 7', False), MenuParameter(8, 'Stufe 8', False), MenuParameter(9, 'Stufe 9', False), MenuParameter(10, 'Stufe 10', False))),
    MenuSetting(51, 35, 'Kraftbegrenzung Tor-Zu', None, False, (MenuParameter(0, 'Stufe 0', False), MenuParameter(1, 'Stufe 1', False), MenuParameter(2, 'Stufe 2', False), MenuParameter(3, 'Stufe 3', False), MenuParameter(4, 'Stufe 4', True), MenuParameter(5, 'Stufe 5', False), MenuParameter(6, 'Stufe 6', False), MenuParameter(7, 'Stufe 7', False), MenuParameter(8, 'Stufe 8', False), MenuParameter(9, 'Stufe 9', False), MenuParameter(10, 'Stufe 10', False))),
    MenuSetting(52, 36, 'Geschwindigkeit Tor-Auf', None, False, (MenuParameter(0, 'Sehr schnell', True), MenuParameter(1, 'Schnell', False), MenuParameter(2, 'Mittel', False), MenuParameter(3, 'Langsam', False))),
    MenuSetting(53, 37, 'Geschwindigkeit Tor-Zu', None, False, (MenuParameter(0, 'Sehr schnell', False), MenuParameter(1, 'Schnell', False), MenuParameter(2, 'Mittel', False), MenuParameter(3, 'Langsam', True))),
    MenuSetting(54, 38, 'Schleichfahrtgeschwindigkeit Tor-Auf', None, False, (MenuParameter(0, 'Maximal', False), MenuParameter(1, 'Mittel', True), MenuParameter(2, 'Langsam', False))),
    MenuSetting(55, 39, 'Schleichfahrtgeschwindigkeit Tor-Zu', None, False, (MenuParameter(0, 'Maximal', False), MenuParameter(1, 'Mittel', True), MenuParameter(2, 'Langsam', False))),
    MenuSetting(56, 40, 'Startpunkte Schleichfahrt Tor-Auf', None, False, (MenuParameter(0, 'Kurz', False), MenuParameter(1, 'Mittel', True), MenuParameter(2, 'Lang', False))),
    MenuSetting(57, 41, 'Startpunkte Schleichfahrt Tor-Zu', None, False, (MenuParameter(0, 'Kurz', False), MenuParameter(1, 'Mittel', True), MenuParameter(2, 'Lang', False))),
    MenuSetting(58, 42, 'Sondertortyp', None, True, (MenuParameter(0, 'Platzhalter', True),)),
    MenuSetting(59, 43, 'Gurtentlastung Tor-Auf', None, False, (MenuParameter(0, 'Ohne', False), MenuParameter(1, 'Kurz', False), MenuParameter(2, 'Standard', True), MenuParameter(3, 'Lang', False))),
    MenuSetting(60, 44, 'Gurtentlastung Tor-Zu', None, False, (MenuParameter(0, 'Ohne', False), MenuParameter(1, 'Kurz', False), MenuParameter(2, 'Standard', True), MenuParameter(3, 'Lang', False))),
    MenuSetting(61, 45, 'Position ändern', None, False, (MenuParameter(0, 'Position Lüften default', True), MenuParameter(1, 'Position ändern', False))),
    MenuSetting(62, 46, 'Reversiergrenzen einstellen', None, False, (MenuParameter(0, 'Stufe 0', True), MenuParameter(1, 'Stufe 1', False), MenuParameter(2, 'Stufe 2', False), MenuParameter(3, 'Stufe 3', True), MenuParameter(4, 'Stufe 4', False), MenuParameter(5, 'Stufe 5', False), MenuParameter(6, 'Stufe 6', True), MenuParameter(7, 'Stufe 7', False), MenuParameter(8, 'Stufe 8', False), MenuParameter(9, 'Stufe 9', False), MenuParameter(10, 'Stufe 10', False))),
    MenuSetting(88, 47, 'Anzeige Antriebstyp und Ausführung (Menu 1-9)', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(89, 48, 'Wartungsanzeige', None, False, (MenuParameter(0, 'deaktiviert', True), MenuParameter(1, '1.000', False), MenuParameter(2, '2.000', False), MenuParameter(3, '3.000', False), MenuParameter(4, '4.000', False), MenuParameter(5, '5.000', False), MenuParameter(6, '7.500', False), MenuParameter(7, '10.000', False), MenuParameter(8, '180 Tage', False), MenuParameter(9, '360 Tage', False))),
    MenuSetting(90, 49, 'Zähler Wartungsanzeige zurück setzen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(91, 50, 'Letzte 10 Fehlermeldungen auslesen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(92, 51, 'Position letzter Kraftfehler anfahren', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(93, 52, 'Fehlerspeicher zurücksetzen/löschen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(94, 53, 'Torzyklen unvollständig auslesen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(95, 54, 'Betriebsstunden gesamt auslesen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(96, 55, 'Reversiergrenzen zurücksetzen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(97, 56, 'Betriebskräfte zurücksetzen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(98, 57, 'Einstellungen Schleichfahrten zurücksetzen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(99, 58, 'Reset', None, True, (MenuParameter(0, 'Zurück', True), MenuParameter(1, 'Reset/Bus Scan HCP2 Bus', False), MenuParameter(2, 'Reset Parameter ab 20-36', False), MenuParameter(3, 'Reset Parameter ab 38-96 (90-95 nicht)', False), MenuParameter(4, 'Werksreset', False))),
    MenuSetting(101, 101, 'Antenne', None, False, (MenuParameter(0, 'Interne Antenne', True), MenuParameter(1, 'Externe Antenne', False))),
)

# --- HET, ProductID=1. Source: menuconcept_het_1_1.json.
_HET_1_1_SETTINGS: Tuple[MenuSetting, ...] = (
    MenuSetting(1, 1, 'Funktion Relais 1', None, False, (MenuParameter(1, 'Tastend', True), MenuParameter(2, 'Schaltend', False))),
    MenuSetting(2, 2, 'Haltezeit Relais 1', None, False, (MenuParameter(1, '1 Sekunde', True), MenuParameter(2, '3 Sekunden', False), MenuParameter(3, '5 Sekunden', False), MenuParameter(4, '10 Sekunden', False), MenuParameter(5, '20 Sekunden', False), MenuParameter(6, '2 Minuten', False))),
    MenuSetting(3, 3, 'Funktion Relais 2', None, False, (MenuParameter(1, 'Tastend', True), MenuParameter(2, 'Schaltend', False))),
    MenuSetting(4, 4, 'Haltezeit Relais 2', None, False, (MenuParameter(1, '1 Sekunde', True), MenuParameter(2, '3 Sekunden', False), MenuParameter(3, '5 Sekunden', False), MenuParameter(4, '10 Sekunden', False), MenuParameter(5, '20 Sekunden', False), MenuParameter(6, '2 Minuten', False))),
    MenuSetting(5, 5, 'Antenne', None, False, (MenuParameter(1, 'Interne Antenne', True), MenuParameter(2, 'Externe Antenne', False))),
)

# --- HET, ProductID=2. Source: menuconcept_het_1_2.json.
_HET_1_2_SETTINGS: Tuple[MenuSetting, ...] = (
    MenuSetting(1, 1, 'Funktion Relais 1', None, False, (MenuParameter(1, 'Tastend', True), MenuParameter(2, 'Schaltend', False))),
    MenuSetting(2, 2, 'Haltezeit Relais 1', None, False, (MenuParameter(1, '1 Sekunde', True), MenuParameter(2, '3 Sekunden', False), MenuParameter(3, '5 Sekunden', False), MenuParameter(4, '10 Sekunden', False), MenuParameter(5, '20 Sekunden', False), MenuParameter(6, '2 Minuten', False))),
    MenuSetting(3, 3, 'Funktion Relais 2', None, False, (MenuParameter(1, 'Tastend', True), MenuParameter(2, 'Schaltend', False))),
    MenuSetting(4, 4, 'Haltezeit Relais 2', None, False, (MenuParameter(1, '1 Sekunde', True), MenuParameter(2, '3 Sekunden', False), MenuParameter(3, '5 Sekunden', False), MenuParameter(4, '10 Sekunden', False), MenuParameter(5, '20 Sekunden', False), MenuParameter(6, '2 Minuten', False))),
    MenuSetting(5, 5, 'Antenne', None, False, (MenuParameter(1, 'Interne Antenne', True), MenuParameter(2, 'Externe Antenne', False))),
)

# --- Rollmatic 2. Source: menuconcept_rm2_01.ad.json.
_ROLLMATIC_2_SETTINGS: Tuple[MenuSetting, ...] = (
    MenuSetting(1, 1, 'Montage des Motors', None, False, (MenuParameter(0, 'Motor links', True), MenuParameter(1, 'Motor rechts', False))),
    MenuSetting(9, 2, 'Inbetriebnahme (unsicherer Totmann Betrieb)', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(10, 3, 'Lernfahrten', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(11, 4, 'Funk lernen: Impuls', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(12, 5, 'Funk lernen: Antriebsbeleuchtung', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(13, 6, 'Funk lernen: Teil-Öffnung', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(14, 7, 'Funk lernen: Tor-Auf', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(15, 8, 'Funk lernen: Tor-Zu', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(16, 9, 'Funk lernen: Lüftungsposition', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(17, 10, 'Alle Funkcodes lernen (Gateway)', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(19, 11, 'Funk löschen', None, False, (MenuParameter(0, 'Zurück', True), MenuParameter(1, 'Funk', False), MenuParameter(2, 'BLE', False), MenuParameter(3, 'WLAN', False), MenuParameter(4, 'Alle', False))),
    MenuSetting(20, 12, 'Reversiergrenze einstellen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(23, 13, 'Position ändern', None, False, (MenuParameter(0, 'Zurück', False), MenuParameter(1, 'Position Teilöffnung ändern', True), MenuParameter(2, 'Position Lüften ändern', False))),
    MenuSetting(24, 14, 'Korrektur Lamellenposition (Grad)', None, False, (MenuParameter(-5, '-5°', False), MenuParameter(-4, '-4°', False), MenuParameter(-3, '-3°', False), MenuParameter(-2, '-2°', False), MenuParameter(-1, '-1°', False), MenuParameter(0, '0°', True), MenuParameter(1, '1°', False), MenuParameter(2, '2°', False), MenuParameter(3, '3°', False), MenuParameter(4, '4°', False), MenuParameter(5, '5°', False))),
    MenuSetting(25, 15, 'Beleuchtung Intern deaktiviert', None, False, (MenuParameter(0, 'Menu deaktiv', False), MenuParameter(1, 'Menu aktiv', True))),
    MenuSetting(26, 16, 'Nachleuchtdauer Intern (durch Antrieb)', None, False, (MenuParameter(0, 'Deaktiviert', False), MenuParameter(1, '30 Sek.', False), MenuParameter(2, '60 Sek.', False), MenuParameter(3, '120 Sek.', True), MenuParameter(4, '180 Sek.', False), MenuParameter(5, '300 Sek.', False), MenuParameter(6, '600 Sek.', False))),
    MenuSetting(27, 17, 'Nachleuchtdauer Externe Beleuchtung', None, False, (MenuParameter(0, 'Deaktiviert', False), MenuParameter(1, '30 Sek.', False), MenuParameter(2, '60 Sek.', False), MenuParameter(3, '180 Sek.', False), MenuParameter(4, '300 Sek.', True), MenuParameter(5, '600 Sek.', False))),
    MenuSetting(28, 18, "Dauer 'EIN'-Funktion externe Beleuchtung über HOR1 oder 3. Relais UAP1 (Schaltbar über Funk bzw. Taster)", None, False, (MenuParameter(0, 'deaktiviert', True), MenuParameter(1, 'aktiviert', False))),
    MenuSetting(30, 19, 'Relasifunktionen Extern HCP HOR1/3 oder UAP1', None, False, (MenuParameter(0, 'Externes Relais deaktiviert', False), MenuParameter(1, 'Funktion Beleuchtung extern', True), MenuParameter(2, "Meldung 'Endlage Tor Auf'", False), MenuParameter(3, "Meldung 'Endlage Tor Zu'", False), MenuParameter(4, "Meldung 'Endlage Teilöffnung'", False), MenuParameter(5, 'Wischsignla bei Befehlsgabe', False), MenuParameter(6, 'Meldung Fehlermeldung auf dem Display (Störung)', False), MenuParameter(7, 'Anfahr-/Vor-/Fahrwarnung Dauersignal', False), MenuParameter(8, 'Anfahr-/Vor-/Fahrwarnung blinkend', False), MenuParameter(9, 'Relais zieht während der Fahrt an', False), MenuParameter(10, 'Meldung Inspektion Anzeige in blinken nach der Fahrt', False), MenuParameter(11, 'Wie interne Beleuchtung/Nachleuchtdauer', False))),
    MenuSetting(31, 20, 'Relaisfunktionen Intern (Italien)', None, False, (MenuParameter(0, 'Internes Relais deaktiviert', False), MenuParameter(1, 'Funktion Beleuchtung extern', False), MenuParameter(2, "Meldung 'Endlage Tor Auf'", False), MenuParameter(3, "Meldung 'Endlage Tor Zu'", False), MenuParameter(4, "Meldung 'Endlage Teilöffnung'", False), MenuParameter(5, 'Wischsignal bei Befehlsgabe', False), MenuParameter(6, 'Meldung Fehlermeldung auf dem Display (Störung)', False), MenuParameter(7, 'Anfahr-/Vor-/Fahrwarnung Dauersignal', False), MenuParameter(8, 'Anfahr-/Vor-/Fahrwarnung blinkend', True), MenuParameter(9, 'Relais zieht während der Fahrt an', False), MenuParameter(10, 'Meldung Inspektion (bei Anzeige in)', False), MenuParameter(11, 'Wie interne Beleuchtung/Nachleuchtdauer', False))),
    MenuSetting(32, 21, 'Vorwarnzeit', None, False, (MenuParameter(0, 'Deaktiviert', True), MenuParameter(1, '1 Sek.', False), MenuParameter(2, '2 Sek.', False), MenuParameter(3, '3 Sek.', False), MenuParameter(4, '4 Sek.', False), MenuParameter(5, '5 Sek.', False), MenuParameter(6, '10 Sek.', False), MenuParameter(7, '15 Sek.', False), MenuParameter(8, '20 Sek.', False), MenuParameter(9, '30 Sek.', False), MenuParameter(10, '60 Sek.', False))),
    MenuSetting(33, 22, 'Vorwarnrichtung', None, False, (MenuParameter(0, 'Vorwarnen in Richtung Zu', True), MenuParameter(1, 'Vorwarnen in Richtung Auf und Zu', False))),
    MenuSetting(34, 23, 'Automatischer Zulauf - Aufhaltezeit', None, False, (MenuParameter(0, 'Deaktiviert', True), MenuParameter(1, '5 Sek.', False), MenuParameter(2, '10 Sek.', False), MenuParameter(3, '15 Sek.', False), MenuParameter(4, '30 Sek.', False), MenuParameter(5, '60 Sek.', False), MenuParameter(6, '90 Sek.', False), MenuParameter(7, '120 Sek.', False), MenuParameter(8, '180 Sek.', False), MenuParameter(9, '240 Sek.', False), MenuParameter(10, '300 Sek.', False))),
    MenuSetting(35, 24, 'Automatischer Zulauf - Aufhaltezeit in Teilöffnung', None, False, (MenuParameter(0, 'Deaktiviert', True), MenuParameter(1, 'wie Menü 34', False), MenuParameter(2, '15 Sek.', False), MenuParameter(3, '30 Sek.', False), MenuParameter(4, '15 Min.', False), MenuParameter(5, '30 Min.', False), MenuParameter(6, '60 Min.', False), MenuParameter(7, '90 Min.', False), MenuParameter(8, '120 Min.', False), MenuParameter(9, '180 Min.', False), MenuParameter(10, '240 Min.', False))),
    MenuSetting(36, 25, 'Bedientasten am Antrieb', None, False, (MenuParameter(0, 'Deaktiviert', False), MenuParameter(1, 'Aktiviert', True))),
    MenuSetting(37, 26, 'Reset', None, False, (MenuParameter(0, 'Zurück', True), MenuParameter(1, 'Reset/Bus Scan HCP2 Bus', False), MenuParameter(2, 'Reset Parameter ab 20 - 36', False), MenuParameter(3, 'Werksreset', False))),
    MenuSetting(38, 27, 'Erweiterte Menüs freigeschaltet', None, False, (MenuParameter(0, 'Platzhalter', True),)),
    MenuSetting(39, 28, 'Impulsverhalten', None, False, (MenuParameter(0, 'Impuls verlängert die Aufhaltezeit (mit allen Befehlsgeräten außer Tor Zu)', True), MenuParameter(1, 'Impuls bricht die Aufhaltezeit ab ( mit allen Befehlsgeräten außer Tor Auf)', False))),
    MenuSetting(40, 29, 'Betriebsart', None, False, (MenuParameter(0, 'Tastbetrieb', False), MenuParameter(1, 'Impulsfolge', True), MenuParameter(2, 'Impulsfolge nur in der Endlage', False), MenuParameter(3, 'sofortige Richtungsumkehr bei Richtungsbefehl', False))),
    MenuSetting(41, 30, 'Sicherheitseinrichtung SE1', None, False, (MenuParameter(0, 'deaktiviert', True), MenuParameter(1, '2-Draht LS statisch / dynamisch', False))),
    MenuSetting(42, 31, 'Sicherheitseinrichtung SE1 Funktion', None, False, (MenuParameter(0, 'Wirkrichtung Tor-Zu kurzes Reversieren', False), MenuParameter(1, 'Wirkrichtung Tor-Zu langes Reversieren', True), MenuParameter(2, 'Wirkrichtung Tor-Zu entlasten', False), MenuParameter(3, 'Wirkrichtung Tor-Auf kurzes Reversieren', False), MenuParameter(4, 'Wirkrichtung Tor-Auf langes Reversieren', False), MenuParameter(5, 'Wirkrichtung Tor-Auf entlasten', False), MenuParameter(6, 'Wirkrichtung Tor-Zu und Tor-Auf kurzes Reversieren', False))),
    MenuSetting(43, 32, 'Sicherheitseinrichtung SE2', None, False, (MenuParameter(0, 'deaktiviert', True), MenuParameter(1, 'SKS', False), MenuParameter(2, 'VL', False), MenuParameter(3, 'Funk-SKS', False), MenuParameter(4, '8k2', False))),
    MenuSetting(44, 33, 'Sicherheitseinrichtung SE2 Funktion', None, False, (MenuParameter(0, 'Wirkrichtung Tor-Zu kurzes Reversieren', False), MenuParameter(1, 'Wirkrichtung Tor-Zu langes Reversieren', True), MenuParameter(2, 'Wirkrichtung Tor-Zu entlasten', False), MenuParameter(3, 'Wirkrichtung Tor-Auf kurzes Reversieren', False), MenuParameter(4, 'Wirkrichtung Tor-Auf langes Reversieren', False), MenuParameter(5, 'Wirkrichtung Tor-Auf entlasten', False), MenuParameter(6, 'Wirkrichtung Tor-Zu und Tor-Auf kurzes Reversieren', False))),
    MenuSetting(48, 34, 'Verhalten bei Ansprechen der Kraftbegrenzung in Wirkrichtung Auf', None, False, (MenuParameter(0, 'Entlasten', True), MenuParameter(1, 'Kurzes Reversieren', False), MenuParameter(2, 'Langes Reversieren', False))),
    MenuSetting(49, 35, 'Verhalten bei Ansprechen der Kraftbegrenzung in Wirkrichtung Zu', None, False, (MenuParameter(0, 'Entlasten', False), MenuParameter(1, 'Kurzes Reversieren', True), MenuParameter(2, 'Langes Reversieren', False))),
    MenuSetting(50, 36, 'Kraftbegrenzung Tor-Auf', None, False, (MenuParameter(0, 'Stufe 0', False), MenuParameter(1, 'Stufe 1', False), MenuParameter(2, 'Stufe 2', False), MenuParameter(3, 'Stufe 3', False), MenuParameter(4, 'Stufe 4', True), MenuParameter(5, 'Stufe 5', False), MenuParameter(6, 'Stufe 6', False), MenuParameter(7, 'Stufe 7', False), MenuParameter(8, 'Stufe 8', False), MenuParameter(9, 'Stufe 9', False), MenuParameter(10, 'Stufe 10', False))),
    MenuSetting(51, 37, 'Kraftbegrenzung Tor-Zu', None, False, (MenuParameter(0, 'Stufe 0', False), MenuParameter(1, 'Stufe 1', False), MenuParameter(2, 'Stufe 2', False), MenuParameter(3, 'Stufe 3', False), MenuParameter(4, 'Stufe 4', True), MenuParameter(5, 'Stufe 5', False), MenuParameter(6, 'Stufe 6', False), MenuParameter(7, 'Stufe 7', False), MenuParameter(8, 'Stufe 8', False), MenuParameter(9, 'Stufe 9', False), MenuParameter(10, 'Stufe 10', False))),
    MenuSetting(52, 38, 'Geschwindigkeit Tor-Auf', None, False, (MenuParameter(0, 'Sehr schnell', True), MenuParameter(1, 'Schnell', False), MenuParameter(2, 'Mittel', False), MenuParameter(3, 'Langsam', False))),
    MenuSetting(53, 39, 'Geschwindigkeit Tor-Zu', None, False, (MenuParameter(0, 'Sehr schnell', False), MenuParameter(1, 'Schnell', False), MenuParameter(2, 'Mittel', True), MenuParameter(3, 'Langsam', False))),
    MenuSetting(54, 40, 'Schleichfahrtgeschwindigkeit Tor-Auf', None, False, (MenuParameter(0, 'Maximal', True), MenuParameter(1, 'Mittel', False), MenuParameter(2, 'Langsam', False))),
    MenuSetting(55, 41, 'Schleichfahrtgeschwindigkeit Tor-Zu', None, False, (MenuParameter(0, 'Maximal', False), MenuParameter(1, 'Mittel', True), MenuParameter(2, 'Langsam', False))),
    MenuSetting(56, 42, 'Startpunkte Schleichfahrt Tor-Auf', None, False, (MenuParameter(0, 'Kurz', False), MenuParameter(1, 'Mittel', True), MenuParameter(2, 'Lang', False))),
    MenuSetting(57, 43, 'Startpunkte Schleichfahrt Tor-Zu', None, False, (MenuParameter(0, 'Kurz', False), MenuParameter(1, 'Mittel', True), MenuParameter(2, 'Lang', False))),
    MenuSetting(58, 44, 'Sondertortyp', None, True, (MenuParameter(0, 'Nicht Gesetzt', True),)),
    MenuSetting(59, 45, 'Gurtentlastung Tor-Auf', None, False, (MenuParameter(0, 'Ohne', False), MenuParameter(1, 'Kurz', True), MenuParameter(2, 'Mittel', False), MenuParameter(3, 'Lang', False))),
    MenuSetting(61, 46, 'Position ändern', None, False, (MenuParameter(0, 'Zurück', True), MenuParameter(1, 'Position ändern', False))),
    MenuSetting(66, 47, 'Max. Lernkräfte', None, False, (MenuParameter(0, 'Stufe 0', True), MenuParameter(1, 'Stufe 1', False), MenuParameter(2, 'Stufe 2', False))),
    MenuSetting(88, 48, 'Anzeige Antriebstyp und Ausführung (Menu 1-9)', None, False, (MenuParameter(1, 'Innen Roller', True), MenuParameter(2, 'Außen Roller', False))),
    MenuSetting(89, 49, 'Wartungsanzeige', None, False, (MenuParameter(0, 'deaktiviert', True), MenuParameter(1, '1.000', False), MenuParameter(2, '2.000', False), MenuParameter(3, '3.000', False), MenuParameter(4, '4.000', False), MenuParameter(5, '5.000', False), MenuParameter(6, '7.500', False), MenuParameter(7, '10.000', False), MenuParameter(8, '180 Tage', False), MenuParameter(9, '360 Tage', False))),
    MenuSetting(90, 50, 'Zähler Wartungsanzeige zurück setzen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(91, 51, 'Letzte 10 Fehlermeldungen auslesen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(92, 52, 'Position letzter Kraftfehler anfahren', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(93, 53, 'Fehlerspeicher zurücksetzen/löschen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(94, 54, 'Torzyklen unvollständig auslesen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(95, 55, 'Betriebsstunden gesamt auslesen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(96, 56, 'Reversiergrenzen zurücksetzen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(97, 57, 'Betriebskräfte zurücksetzen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(98, 58, 'Einstellungen Schleichfahrten zurücksetzen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(99, 59, 'Reset', None, True, (MenuParameter(0, 'Zurück', True), MenuParameter(1, 'Reset/Bus Scan HCP2 Bus', False), MenuParameter(2, 'Reset Parameter ab 20-36', False), MenuParameter(3, 'Reset Parameter ab 38-96 (90-95 nicht)', False), MenuParameter(4, 'Werksreset Rollmatic (U)', False), MenuParameter(5, 'Werksreset unmontiert (UU)', False))),
    MenuSetting(101, 101, 'Antenne', None, False, (MenuParameter(0, 'Interne Antenne', True), MenuParameter(1, 'Externe Antenne', False))),
)

# --- SilentDrive 2, firmware EE002449-00.aa. Source: menuconcept_sd2_00_aa.json.
_SILENTDRIVE_2_AA_SETTINGS: Tuple[MenuSetting, ...] = (
    MenuSetting(1, 1, 'Sectionaltor', None, True, (MenuParameter(0, 'Deaktivieren', False), MenuParameter(1, 'Aktivieren', True))),
    MenuSetting(10, 2, 'Lernfahrten', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(11, 3, 'Reversiergrenze Einstellen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(12, 4, 'Funk lernen: Impuls', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(13, 5, 'Funk lernen: Beleuchtung', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(14, 6, 'Funk lernen: Teilöffnung', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(15, 7, 'Funk lernen: Tor-Auf', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(16, 8, 'Funk lernen: Tor-Zu', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(17, 9, 'Funk lernen: Lüftungsposition', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(18, 10, 'Position Ändern Teilöffnung', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(19, 11, 'Position Ändern Lüftungsposition', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(20, 12, 'Aufhaltezeit Auf Aktiv', None, False, (MenuParameter(0, 'Deaktivieren', True), MenuParameter(1, 'Aktivieren', False))),
    MenuSetting(21, 13, 'Aufhaltezeit Teilöffnung Aktiv', None, False, (MenuParameter(0, 'Deaktivieren', True), MenuParameter(1, 'Aktivieren', False))),
    MenuSetting(22, 14, 'Bus Scan', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(23, 15, 'Funk Löschen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(24, 16, 'Bluetooth Löschen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(25, 17, 'Werksreset', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(26, 18, 'Freigabe Expertenbereich', None, False, (MenuParameter(0, 'Platzhalter', True),)),
    MenuSetting(27, 19, 'Schwingtor', None, False, (MenuParameter(0, 'Deaktivieren', True), MenuParameter(1, 'Aktivieren', False))),
    MenuSetting(28, 20, 'Wartungsanzeige', None, False, (MenuParameter(0, '360 Tage / 2000 Zyklen', True), MenuParameter(1, '1.000', False), MenuParameter(2, '2.000', False), MenuParameter(3, '3.000', False), MenuParameter(4, '4.000', False), MenuParameter(5, '5.000', False), MenuParameter(6, '7.500', False), MenuParameter(7, '10.000', False), MenuParameter(8, '180 Tage', False), MenuParameter(9, '360 Tage', False))),
    MenuSetting(29, 21, 'Zähler Wartungsanzeige zurück setzen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(30, 22, 'Letzte 10 Fehlermeldungen auslesen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(31, 23, 'Position letzter Kraftfehler anfahren', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(32, 24, 'Fehlerspeicher zurücksetzen/löschen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(33, 25, 'Torzyklen unvollständig auslesen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(34, 26, 'Betriebsstunden gesamt auslesen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(35, 27, 'Betriebskräfte zurücksetzen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(36, 28, 'Automatischer Zulauf - Aufhaltezeit', None, False, (MenuParameter(1, '30 Sekunden', False), MenuParameter(2, '60 Sekunden', True), MenuParameter(3, '90 Sekunden', False), MenuParameter(4, '120 Sekunden', False), MenuParameter(5, '180 Sekunden', False), MenuParameter(6, '240 Sekunden', False), MenuParameter(7, '300 Sekunden', False), MenuParameter(8, '600 Sekunden', False), MenuParameter(9, '1800 Sekunden', False), MenuParameter(10, '3600 Sekunden', False))),
    MenuSetting(37, 29, 'Automatischer Zulauf - Aufhaltezeit in Teilöffnung', None, False, (MenuParameter(1, '15 Sekunden', False), MenuParameter(2, '30 Sekunden', True), MenuParameter(3, '60 Sekunden', False), MenuParameter(4, '90 Sekunden', False), MenuParameter(5, '120 Sekunden', False), MenuParameter(6, '180 Sekunden', False), MenuParameter(7, '240 Sekunden', False), MenuParameter(8, '300 Sekunden', False), MenuParameter(9, '600 Sekunden', False), MenuParameter(10, '1800 Sekunden', False))),
    MenuSetting(38, 30, 'Gurtentlastung Tor-Zu', None, False, (MenuParameter(0, 'Ohne', True), MenuParameter(1, 'Kurz', False), MenuParameter(2, 'Mittel', False), MenuParameter(3, 'Lang', False))),
    MenuSetting(39, 31, 'Gurtentlastung Tor-Auf', None, False, (MenuParameter(0, 'Ohne', False), MenuParameter(1, 'Kurz', False), MenuParameter(2, 'Mittel', True), MenuParameter(3, 'Lang', False))),
    MenuSetting(40, 32, 'Beleuchtung Intern deaktiviert', None, False, (MenuParameter(0, 'Menu deaktiviert', False), MenuParameter(1, 'Menu aktiv', True))),
    MenuSetting(41, 33, 'Nachleuchtdauer Intern (durch Antrieb)', None, False, (MenuParameter(0, 'Zurück', False), MenuParameter(1, '30 Sek.', False), MenuParameter(2, '60 Sek.', False), MenuParameter(3, '120 Sek.', False), MenuParameter(4, '180 Sek.', True), MenuParameter(5, '300 Sek.', False))),
    MenuSetting(42, 34, 'Nachleuchtdauer Externe Beleuchtung', None, False, (MenuParameter(0, 'Zurück', False), MenuParameter(1, 'wie Menü 26', True), MenuParameter(2, '60 Sek.', False), MenuParameter(3, '120 Sek.', False), MenuParameter(4, '180 Sek.', True), MenuParameter(5, '300 Sek.', False), MenuParameter(6, '600 Sek.', False))),
    MenuSetting(43, 35, "Dauer 'EIN'-Funktion externe Beleuchtung über HOR1 oder 3. Relais UAP1 (Schaltbar über Funk bzw. Taster)", None, False, (MenuParameter(0, 'deaktiviert', True), MenuParameter(1, 'aktiviert', False))),
    MenuSetting(44, 36, 'Lauflicht', None, False, (MenuParameter(0, 'Deaktiviert', True), MenuParameter(1, 'Aktiviert bei Torfahrt', False), MenuParameter(2, 'Aktiviert bei Anfahr-/ Vorwarnung', False), MenuParameter(3, 'Aktiviert bei Torfahrt und Anfahr-/ Vorwarnung', False), MenuParameter(4, 'Aktiviert bei Torfahrt (Laufrichtung invertiert)', False), MenuParameter(5, 'Aktiviert bei Anfahr-/ Vorwarnung (Laufrichtung invertiert)', False), MenuParameter(6, 'Aktiviert bei Torfahrt und Anfahr-/ Vorwarnung (Laufrichtung invertiert)', False))),
    MenuSetting(45, 37, 'Relasifunktionen Extern HCP HOR1/3 oder UAP1', None, False, (MenuParameter(0, 'Externes Relais deaktiviert', False), MenuParameter(1, 'Funktion Beleuchtung extern', True), MenuParameter(2, "Meldung 'Endlage Tor Auf'", False), MenuParameter(3, "Meldung 'Endlage Tor Zu'", False), MenuParameter(4, "Meldung 'Endlage Teilöffnung'", False), MenuParameter(5, 'Wischsignal bei Befehlsgabe', False), MenuParameter(6, 'Meldung Fehlermeldung auf dem Display (Störung)', False), MenuParameter(7, 'Anfahr-/Vor-/Fahrwarnung Dauersignal', False), MenuParameter(8, 'Anfahr-/Vor-/Fahrwarnung blinkend', False), MenuParameter(9, 'Relais zieht während der Fahrt an', False), MenuParameter(10, 'Meldung Inspektion bei Anzeige in', False), MenuParameter(11, 'Wie interne Beleuchtung/Nachleuchtdauer', False))),
    MenuSetting(46, 38, 'Vorwarnzeit', None, False, (MenuParameter(0, 'Deaktiviert', True), MenuParameter(1, '5 Sek.', False))),
    MenuSetting(47, 39, 'Vorwarnrichtung', None, False, (MenuParameter(0, 'Vorwarnen in Richtung Zu', False), MenuParameter(1, 'Vorwarnen in Richtung Auf und Zu', True))),
    MenuSetting(48, 40, 'Bedientasten am Antrieb', None, False, (MenuParameter(0, 'Deaktiviert', False), MenuParameter(1, 'Aktiviert', True))),
    MenuSetting(49, 41, 'Impulsverhalten', None, False, (MenuParameter(0, 'Impuls verlängert die Aufhaltezeit (mit allen Befehlsgeräten außer Tor Zu)', True), MenuParameter(1, 'Impuls bricht die Aufhaltezeit ab ( mit allen Befehlsgeräten außer Tor Auf)', False))),
    MenuSetting(50, 42, 'Betriebsart', None, False, (MenuParameter(1, 'Impulsfolge', True), MenuParameter(2, 'Impulsfolge nur in der Endlage', False), MenuParameter(3, 'sofortige Richtungsumkehr bei Richtungsbefehl', False))),
    MenuSetting(51, 43, 'Sicherheitseinrichtung SE1', None, False, (MenuParameter(0, 'deaktiviert', False), MenuParameter(1, '2-Draht LS statisch / dynamisch', True))),
    MenuSetting(52, 44, 'Sicherheitseinrichtung SE1 Funktion', None, False, (MenuParameter(0, 'Wirkrichtung Tor-Zu kurzes Reversieren', False), MenuParameter(1, 'Wirkrichtung Tor-Zu langes Reversieren', True), MenuParameter(2, 'Wirkrichtung Tor-Zu entlasten', False), MenuParameter(3, 'Wirkrichtung Tor-Auf kurzes Reversieren', False), MenuParameter(4, 'Wirkrichtung Tor-Auf langes Reversieren', False), MenuParameter(5, 'Wirkrichtung Tor-Auf entlasten', False), MenuParameter(6, 'Wirkrichtung Tor-Zu und Tor-Auf kurzes Reversieren', False))),
    MenuSetting(53, 45, 'Verhalten bei Ansprechen der Kraftbegrenzung in Wirkrichtung Auf', None, False, (MenuParameter(0, 'Entlasten', True), MenuParameter(1, 'Kurzes Reversieren', False))),
    MenuSetting(54, 46, 'Verhalten bei Ansprechen der Kraftbegrenzung in Wirkrichtung Zu', None, False, (MenuParameter(0, 'Entlasten', False), MenuParameter(1, 'Kurzes Reversieren', False), MenuParameter(2, 'Langes Reversieren', True))),
    MenuSetting(55, 47, 'Kraftbegrenzung Tor-Auf', None, False, (MenuParameter(0, 'Stufe 0', False), MenuParameter(1, 'Stufe 1', False), MenuParameter(2, 'Stufe 2', False), MenuParameter(3, 'Stufe 3', False), MenuParameter(4, 'Stufe 4', False), MenuParameter(5, 'Stufe 5', False), MenuParameter(6, 'Stufe 6', False), MenuParameter(7, 'Stufe 7', False), MenuParameter(8, 'Stufe 8', False), MenuParameter(9, 'Stufe 9', True), MenuParameter(10, 'Stufe 10', False))),
    MenuSetting(56, 48, 'Kraftbegrenzung Tor-Zu', None, False, (MenuParameter(0, 'Stufe 0', False), MenuParameter(1, 'Stufe 1', False), MenuParameter(2, 'Stufe 2', False), MenuParameter(3, 'Stufe 3', False), MenuParameter(4, 'Stufe 4', False), MenuParameter(5, 'Stufe 5', False), MenuParameter(6, 'Stufe 6', False), MenuParameter(7, 'Stufe 7', False), MenuParameter(8, 'Stufe 8', False), MenuParameter(9, 'Stufe 9', True), MenuParameter(10, 'Stufe 10', False))),
    MenuSetting(57, 49, 'Geschwindigkeit Tor-Auf', None, False, (MenuParameter(0, 'Sehr schnell', True), MenuParameter(1, 'Schnell', False), MenuParameter(2, 'Mittel', False), MenuParameter(3, 'Langsam', False))),
    MenuSetting(58, 50, 'Geschwindigkeit Tor-Zu', None, False, (MenuParameter(0, 'Sehr schnell', True), MenuParameter(1, 'Schnell', False), MenuParameter(2, 'Mittel', False), MenuParameter(3, 'Langsam', False))),
    MenuSetting(59, 51, 'Schleichfahrtgeschwindigkeit Tor-Auf', None, False, (MenuParameter(0, 'Maximal', False), MenuParameter(1, 'Mittel', True), MenuParameter(2, 'Langsam', False))),
    MenuSetting(60, 52, 'Schleichfahrtgeschwindigkeit Tor-Zu', None, False, (MenuParameter(0, 'Maximal', False), MenuParameter(1, 'Mittel', True), MenuParameter(2, 'Langsam', False))),
    MenuSetting(61, 53, 'Startpunkte Schleichfahrt Tor-Auf', None, False, (MenuParameter(0, 'Kurz', False), MenuParameter(1, 'Mittel', True), MenuParameter(2, 'Lang', False))),
    MenuSetting(62, 54, 'Startpunkte Schleichfahrt Tor-Zu', None, False, (MenuParameter(0, 'Kurz', False), MenuParameter(1, 'Mittel', True), MenuParameter(2, 'Lang', False))),
    MenuSetting(101, 101, 'Antenne', None, False, (MenuParameter(0, 'Interne Antenne', True), MenuParameter(1, 'Externe Antenne', False))),
)

# --- SilentDrive 2, firmware EE002449-00.ai (later revision, same ProductID=33
# as above - a genuine firmware-revision variant, unlike the sm4_01/sm4_02
# split). Source: menuconcept_sd2_00_ai.json.
_SILENTDRIVE_2_AI_SETTINGS: Tuple[MenuSetting, ...] = (
    MenuSetting(1, 1, 'Sectionaltor', None, True, (MenuParameter(0, 'Deaktivieren', False), MenuParameter(1, 'Aktivieren', True))),
    MenuSetting(10, 2, 'Lernfahrten', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(11, 3, 'Reversiergrenze Einstellen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(12, 4, 'Funk lernen: Impuls', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(13, 5, 'Funk lernen: Beleuchtung', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(14, 6, 'Funk lernen: Teilöffnung', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(15, 7, 'Funk lernen: Tor-Auf', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(16, 8, 'Funk lernen: Tor-Zu', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(17, 9, 'Funk lernen: Lüftungsposition', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(18, 10, 'Position Ändern Teilöffnung', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(19, 11, 'Position Ändern Lüftungsposition', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(20, 12, 'Aufhaltezeit Auf Aktiv', None, False, (MenuParameter(0, 'Deaktivieren', True), MenuParameter(1, 'Aktivieren', False))),
    MenuSetting(21, 13, 'Aufhaltezeit Teilöffnung Aktiv', None, False, (MenuParameter(0, 'Deaktivieren', True), MenuParameter(1, 'Aktivieren', False))),
    MenuSetting(22, 14, 'Bus Scan', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(23, 15, 'Funk Löschen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(24, 16, 'Bluetooth Löschen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(25, 17, 'Werksreset', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(26, 18, 'Freigabe Expertenbereich', None, False, (MenuParameter(0, 'Platzhalter', True),)),
    MenuSetting(27, 19, 'Schwingtor', None, False, (MenuParameter(0, 'Deaktivieren', True), MenuParameter(1, 'Aktivieren', False))),
    MenuSetting(28, 20, 'Offset Lernkraft', None, False, (MenuParameter(0, 'Deaktivieren', True), MenuParameter(1, 'Aktivieren', False))),
    MenuSetting(29, 21, 'Wartungsanzeige', None, False, (MenuParameter(0, '360 Tage / 2000 Zyklen', True), MenuParameter(1, '1.000', False), MenuParameter(2, '2.000', False), MenuParameter(3, '3.000', False), MenuParameter(4, '4.000', False), MenuParameter(5, '5.000', False), MenuParameter(6, '7.500', False), MenuParameter(7, '10.000', False), MenuParameter(8, '180 Tage', False), MenuParameter(9, '360 Tage', False))),
    MenuSetting(30, 22, 'Zähler Wartungsanzeige zurück setzen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(31, 23, 'Letzte 10 Fehlermeldungen auslesen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(32, 24, 'Position letzter Kraftfehler anfahren', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(33, 25, 'Fehlerspeicher zurücksetzen/löschen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(34, 26, 'Torzyklen unvollständig auslesen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(35, 27, 'Betriebsstunden gesamt auslesen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(36, 28, 'Betriebskräfte zurücksetzen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(37, 29, 'Automatischer Zulauf - Aufhaltezeit', None, False, (MenuParameter(1, '30 Sekunden', False), MenuParameter(2, '60 Sekunden', True), MenuParameter(3, '90 Sekunden', False), MenuParameter(4, '120 Sekunden', False), MenuParameter(5, '180 Sekunden', False), MenuParameter(6, '240 Sekunden', False), MenuParameter(7, '300 Sekunden', False), MenuParameter(8, '600 Sekunden', False), MenuParameter(9, '1800 Sekunden', False), MenuParameter(10, '3600 Sekunden', False))),
    MenuSetting(38, 30, 'Automatischer Zulauf - Aufhaltezeit in Teilöffnung', None, False, (MenuParameter(1, '15 Sekunden', False), MenuParameter(2, '30 Sekunden', True), MenuParameter(3, '60 Sekunden', False), MenuParameter(4, '90 Sekunden', False), MenuParameter(5, '120 Sekunden', False), MenuParameter(6, '180 Sekunden', False), MenuParameter(7, '240 Sekunden', False), MenuParameter(8, '300 Sekunden', False), MenuParameter(9, '600 Sekunden', False), MenuParameter(10, '1800 Sekunden', False))),
    MenuSetting(39, 31, 'Gurtentlastung Tor-Zu', None, False, (MenuParameter(0, 'Ohne', True), MenuParameter(1, 'Kurz', False), MenuParameter(2, 'Mittel', False), MenuParameter(3, 'Lang', False))),
    MenuSetting(40, 32, 'Gurtentlastung Tor-Auf', None, False, (MenuParameter(0, 'Ohne', False), MenuParameter(1, 'Kurz', False), MenuParameter(2, 'Mittel', True), MenuParameter(3, 'Lang', False))),
    MenuSetting(41, 33, 'Beleuchtung Intern deaktiviert', None, False, (MenuParameter(0, 'Menu deaktiviert', False), MenuParameter(1, 'Menu aktiv', True))),
    MenuSetting(42, 34, 'Nachleuchtdauer Intern (durch Antrieb)', None, False, (MenuParameter(0, 'Zurück', False), MenuParameter(1, '30 Sek.', False), MenuParameter(2, '60 Sek.', False), MenuParameter(3, '120 Sek.', False), MenuParameter(4, '180 Sek.', True), MenuParameter(5, '300 Sek.', False))),
    MenuSetting(43, 35, 'Nachleuchtdauer Externe Beleuchtung', None, False, (MenuParameter(0, 'Zurück', False), MenuParameter(1, 'wie Menü 26', True), MenuParameter(2, '60 Sek.', False), MenuParameter(3, '120 Sek.', False), MenuParameter(4, '180 Sek.', True), MenuParameter(5, '300 Sek.', False), MenuParameter(6, '600 Sek.', False))),
    MenuSetting(44, 36, "Dauer 'EIN'-Funktion externe Beleuchtung über HOR1 oder 3. Relais UAP1 (Schaltbar über Funk bzw. Taster)", None, False, (MenuParameter(0, 'deaktiviert', True), MenuParameter(1, 'aktiviert', False))),
    MenuSetting(45, 37, 'Lauflicht', None, False, (MenuParameter(0, 'Deaktiviert', True), MenuParameter(1, 'Aktiviert bei Torfahrt', False), MenuParameter(2, 'Aktiviert bei Anfahr-/ Vorwarnung', False), MenuParameter(3, 'Aktiviert bei Torfahrt und Anfahr-/ Vorwarnung', False), MenuParameter(4, 'Aktiviert bei Torfahrt (Laufrichtung invertiert)', False), MenuParameter(5, 'Aktiviert bei Anfahr-/ Vorwarnung (Laufrichtung invertiert)', False), MenuParameter(6, 'Aktiviert bei Torfahrt und Anfahr-/ Vorwarnung (Laufrichtung invertiert)', False))),
    MenuSetting(46, 38, 'Relasifunktionen Extern HCP HOR1/3 oder UAP1', None, False, (MenuParameter(0, 'Externes Relais deaktiviert', False), MenuParameter(1, 'Funktion Beleuchtung extern', True), MenuParameter(2, "Meldung 'Endlage Tor Auf'", False), MenuParameter(3, "Meldung 'Endlage Tor Zu'", False), MenuParameter(4, "Meldung 'Endlage Teilöffnung'", False), MenuParameter(5, 'Wischsignal bei Befehlsgabe', False), MenuParameter(6, 'Meldung Fehlermeldung auf dem Display (Störung)', False), MenuParameter(7, 'Anfahr-/Vor-/Fahrwarnung Dauersignal', False), MenuParameter(8, 'Anfahr-/Vor-/Fahrwarnung blinkend', False), MenuParameter(9, 'Relais zieht während der Fahrt an', False), MenuParameter(10, 'Meldung Inspektion bei Anzeige in', False), MenuParameter(11, 'Wie interne Beleuchtung/Nachleuchtdauer', False))),
    MenuSetting(47, 39, 'Vorwarnzeit', None, False, (MenuParameter(0, 'Deaktiviert', True), MenuParameter(1, '5 Sek.', False))),
    MenuSetting(48, 40, 'Vorwarnrichtung', None, False, (MenuParameter(0, 'Vorwarnen in Richtung Zu', False), MenuParameter(1, 'Vorwarnen in Richtung Auf und Zu', True))),
    MenuSetting(49, 41, 'Bedientasten am Antrieb', None, False, (MenuParameter(0, 'Deaktiviert', False), MenuParameter(1, 'Aktiviert', True))),
    MenuSetting(50, 42, 'Impulsverhalten', None, False, (MenuParameter(0, 'Impuls verlängert die Aufhaltezeit (mit allen Befehlsgeräten außer Tor Zu)', True), MenuParameter(1, 'Impuls bricht die Aufhaltezeit ab ( mit allen Befehlsgeräten außer Tor Auf)', False))),
    MenuSetting(51, 43, 'Betriebsart', None, False, (MenuParameter(1, 'Impulsfolge', True), MenuParameter(2, 'Impulsfolge nur in der Endlage', False), MenuParameter(3, 'sofortige Richtungsumkehr bei Richtungsbefehl', False))),
    MenuSetting(52, 44, 'Sicherheitseinrichtung SE1', None, False, (MenuParameter(0, 'deaktiviert', False), MenuParameter(1, '2-Draht LS statisch / dynamisch', True))),
    MenuSetting(53, 45, 'Sicherheitseinrichtung SE1 Funktion', None, False, (MenuParameter(0, 'Wirkrichtung Tor-Zu kurzes Reversieren', False), MenuParameter(1, 'Wirkrichtung Tor-Zu langes Reversieren', True), MenuParameter(2, 'Wirkrichtung Tor-Zu entlasten', False), MenuParameter(3, 'Wirkrichtung Tor-Auf kurzes Reversieren', False), MenuParameter(4, 'Wirkrichtung Tor-Auf langes Reversieren', False), MenuParameter(5, 'Wirkrichtung Tor-Auf entlasten', False), MenuParameter(6, 'Wirkrichtung Tor-Zu und Tor-Auf kurzes Reversieren', False))),
    MenuSetting(54, 46, 'Verhalten bei Ansprechen der Kraftbegrenzung in Wirkrichtung Auf', None, False, (MenuParameter(0, 'Entlasten', True), MenuParameter(1, 'Kurzes Reversieren', False))),
    MenuSetting(55, 47, 'Verhalten bei Ansprechen der Kraftbegrenzung in Wirkrichtung Zu', None, False, (MenuParameter(0, 'Entlasten', False), MenuParameter(1, 'Kurzes Reversieren', False), MenuParameter(2, 'Langes Reversieren', True))),
    MenuSetting(56, 48, 'Kraftbegrenzung Tor-Auf', None, False, (MenuParameter(0, 'Stufe 0', False), MenuParameter(1, 'Stufe 1', False), MenuParameter(2, 'Stufe 2', False), MenuParameter(3, 'Stufe 3', False), MenuParameter(4, 'Stufe 4', False), MenuParameter(5, 'Stufe 5', False), MenuParameter(6, 'Stufe 6', False), MenuParameter(7, 'Stufe 7', False), MenuParameter(8, 'Stufe 8', False), MenuParameter(9, 'Stufe 9', True), MenuParameter(10, 'Stufe 10', False))),
    MenuSetting(57, 49, 'Kraftbegrenzung Tor-Zu', None, False, (MenuParameter(0, 'Stufe 0', False), MenuParameter(1, 'Stufe 1', False), MenuParameter(2, 'Stufe 2', False), MenuParameter(3, 'Stufe 3', False), MenuParameter(4, 'Stufe 4', False), MenuParameter(5, 'Stufe 5', False), MenuParameter(6, 'Stufe 6', False), MenuParameter(7, 'Stufe 7', False), MenuParameter(8, 'Stufe 8', False), MenuParameter(9, 'Stufe 9', True), MenuParameter(10, 'Stufe 10', False))),
    MenuSetting(58, 50, 'Geschwindigkeit Tor-Auf', None, False, (MenuParameter(0, 'Sehr schnell', True), MenuParameter(1, 'Schnell', False), MenuParameter(2, 'Mittel', False), MenuParameter(3, 'Langsam', False))),
    MenuSetting(59, 51, 'Geschwindigkeit Tor-Zu', None, False, (MenuParameter(0, 'Sehr schnell', True), MenuParameter(1, 'Schnell', False), MenuParameter(2, 'Mittel', False), MenuParameter(3, 'Langsam', False))),
    MenuSetting(60, 52, 'Schleichfahrtgeschwindigkeit Tor-Auf', None, False, (MenuParameter(0, 'Maximal', False), MenuParameter(1, 'Mittel', True), MenuParameter(2, 'Langsam', False))),
    MenuSetting(61, 53, 'Schleichfahrtgeschwindigkeit Tor-Zu', None, False, (MenuParameter(0, 'Maximal', False), MenuParameter(1, 'Mittel', True), MenuParameter(2, 'Langsam', False))),
    MenuSetting(62, 54, 'Startpunkte Schleichfahrt Tor-Auf', None, False, (MenuParameter(0, 'Kurz', False), MenuParameter(1, 'Mittel', True), MenuParameter(2, 'Lang', False))),
    MenuSetting(63, 55, 'Startpunkte Schleichfahrt Tor-Zu', None, False, (MenuParameter(0, 'Kurz', False), MenuParameter(1, 'Mittel', True), MenuParameter(2, 'Lang', False))),
    MenuSetting(64, 56, 'Überwachung Schlupftürkontakt', None, False, (MenuParameter(0, 'Schlupftürkontakt deaktiviert ( oder ohne Testung)', True), MenuParameter(1, 'Schlupftürkontakt mit Testung', False))),
    MenuSetting(101, 101, 'Antenne', None, False, (MenuParameter(0, 'Interne Antenne', True), MenuParameter(1, 'Externe Antenne', False))),
)

# --- Supramatic 4 H4. Source: menuconcept_smh4_00_aa.json.
_SUPRAMATIC_4_H4_SETTINGS: Tuple[MenuSetting, ...] = (
    MenuSetting(1, 1, 'Torart', None, False, (MenuParameter(0, 'Sektionaltor', True), MenuParameter(1, 'Schwingtor', False), MenuParameter(2, 'Seiten-Sektionaltor', False), MenuParameter(3, 'Kipptor', False), MenuParameter(4, 'Decken-Gliedertor', False), MenuParameter(5, 'Canopy Tor', False))),
    MenuSetting(10, 2, 'Lernfahrten', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(11, 3, 'Funk lernen: Impuls', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(12, 4, 'Funk lernen: Antriebsbeleuchtung', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(13, 5, 'Funk lernen: Teil-Öffnung', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(14, 6, 'Funk lernen: Tor-Auf', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(15, 7, 'Funk lernen: Tor-Zu', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(16, 8, 'Funk lernen: Lüftungsposition', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(17, 9, 'Alle Funkcodes lernen (Gateway)', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(18, 10, 'WLAN', None, False, (MenuParameter(0, 'Deaktivieren', True), MenuParameter(1, 'Aktivieren', False))),
    MenuSetting(19, 11, 'Funk löschen', None, False, (MenuParameter(0, 'Zurück', True), MenuParameter(1, 'Funk', False), MenuParameter(2, 'BLE', False), MenuParameter(3, 'WLAN', False), MenuParameter(4, 'Alle', False))),
    MenuSetting(20, 12, 'Reversiergrenze einstellen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(21, 13, 'Überwachung Schlupftürkontakt', None, False, (MenuParameter(0, 'Schlupftürkontakt deaktiviert ( oder ohne Testung)', True), MenuParameter(1, 'Schlupftürkontakt mit Testung', False))),
    MenuSetting(22, 14, 'Gurtentlastung Tor-Zu', None, False, (MenuParameter(0, 'ohne', False), MenuParameter(1, 'Kurz', True), MenuParameter(2, 'Mittel', False), MenuParameter(3, 'Lang', False))),
    MenuSetting(23, 15, 'Position ändern', None, False, (MenuParameter(0, 'Zurück', True), MenuParameter(1, 'Position Teilöffnung ändern', False), MenuParameter(2, 'Position Lüften ändern', False))),
    MenuSetting(24, 16, 'ETV Verriegelungselement', None, False, (MenuParameter(0, 'deaktiviert', True), MenuParameter(1, 'aktiviert', False))),
    MenuSetting(25, 17, 'Beleuchtung Intern deaktiviert', None, False, (MenuParameter(0, 'Menu deaktiv', False), MenuParameter(1, 'Menu aktiv', True))),
    MenuSetting(26, 18, 'Nachleuchtdauer Intern (durch Antrieb)', None, False, (MenuParameter(0, 'Deaktiviert', False), MenuParameter(1, '30 Sek.', False), MenuParameter(2, '60 Sek.', False), MenuParameter(3, '120 Sek.', True), MenuParameter(4, '180 Sek.', False), MenuParameter(5, '300 Sek.', False), MenuParameter(6, '600 Sek.', False))),
    MenuSetting(27, 19, 'Nachleuchtdauer Externe Beleuchtung', None, False, (MenuParameter(0, 'Deaktiviert', False), MenuParameter(1, '30 Sek.', False), MenuParameter(2, '60 Sek.', False), MenuParameter(3, '180 Sek.', False), MenuParameter(4, '300 Sek.', True), MenuParameter(5, '600 Sek.', False))),
    MenuSetting(28, 20, "Dauer 'EIN'-Funktion externe Beleuchtung über HOR1 oder 3. Relais UAP1 (Schaltbar über Funk bzw. Taster)", None, False, (MenuParameter(0, 'deaktiviert', True), MenuParameter(1, 'aktiviert', False))),
    MenuSetting(29, 21, 'Lauflicht', None, False, (MenuParameter(0, 'Deaktiviert', True), MenuParameter(1, 'Aktiviert bei Torfahrt', False), MenuParameter(2, 'Aktiviert bei Anfahr-/ Vorwarnung', False), MenuParameter(3, 'Aktiviert bei Torfahrt und Anfahr-/ Vorwarnung', False), MenuParameter(4, 'Aktiviert bei Torfahrt (Laufrichtung invertiert)', False), MenuParameter(5, 'Aktiviert bei Anfahr-/ Vorwarnung (Laufrichtung invertiert)', False), MenuParameter(6, 'Aktiviert bei Torfahrt und Anfahr-/ Vorwarnung (Laufrichtung invertiert)', False))),
    MenuSetting(30, 22, 'Relasifunktionen Extern HCP HOR1/3 oder UAP1', None, False, (MenuParameter(0, 'Externes Relais deaktiviert', False), MenuParameter(1, 'Funktion Beleuchtung extern', True), MenuParameter(2, "Meldung 'Endlage Tor Auf'", False), MenuParameter(3, "Meldung 'Endlage Tor Zu'", False), MenuParameter(4, "Meldung 'Endlage Teilöffnung'", False), MenuParameter(5, 'Wischsignal bei Befehlsgabe', False), MenuParameter(6, 'Meldung Fehlermeldung auf dem Display (Störung)', False), MenuParameter(7, 'Anfahr-/Vor-/Fahrwarnung Dauersignal', False), MenuParameter(8, 'Anfahr-/Vor-/Fahrwarnung blinkend', False), MenuParameter(9, 'Relais zieht während der Fahrt an', False), MenuParameter(10, 'Meldung Inspektion bei Anzeige in', False), MenuParameter(11, 'Wie interne Beleuchtung/Nachleuchtdauer', False))),
    MenuSetting(32, 23, 'Vorwarnzeit', None, False, (MenuParameter(0, 'Deaktiviert', True), MenuParameter(1, '1 Sek.', False), MenuParameter(2, '2 Sek.', False), MenuParameter(3, '3 Sek.', False), MenuParameter(4, '4 Sek.', False), MenuParameter(5, '5 Sek.', False), MenuParameter(6, '10 Sek.', False), MenuParameter(7, '15 Sek.', False), MenuParameter(8, '20 Sek.', False), MenuParameter(9, '30 Sek.', False), MenuParameter(10, '60 Sek.', False))),
    MenuSetting(33, 24, 'Vorwarnrichtung', None, False, (MenuParameter(0, 'Vorwarnen in Richtung Zu', True), MenuParameter(1, 'Vorwarnen in Richtung Auf und Zu', False))),
    MenuSetting(34, 25, 'Automatischer Zulauf - Aufhaltezeit', None, False, (MenuParameter(0, 'Deaktiviert', True), MenuParameter(1, '5 Sek.', False), MenuParameter(2, '10 Sek.', False), MenuParameter(3, '15 Sek.', False), MenuParameter(4, '30 Sek.', False), MenuParameter(5, '60 Sek.', False), MenuParameter(6, '90 Sek.', False), MenuParameter(7, '120 Sek.', False), MenuParameter(8, '180 Sek.', False), MenuParameter(9, '240 Sek.', False), MenuParameter(10, '300 Sek.', False))),
    MenuSetting(35, 26, 'Automatischer Zulauf - Aufhaltezeit in Teilöffnung', None, False, (MenuParameter(0, 'Deaktiviert', True), MenuParameter(1, 'wie Menü 34', False), MenuParameter(2, '15 Sek.', False), MenuParameter(3, '30 Sek.', False), MenuParameter(4, '15 Min.', False), MenuParameter(5, '30 Min.', False), MenuParameter(6, '60 Min.', False), MenuParameter(7, '90 Min.', False), MenuParameter(8, '120 Min.', False), MenuParameter(9, '180 Min.', False), MenuParameter(10, '240 Min.', False))),
    MenuSetting(36, 27, 'Bedientasten am Antrieb', None, False, (MenuParameter(0, 'Deaktiviert', False), MenuParameter(1, 'Aktiviert', True))),
    MenuSetting(37, 28, 'Reset', None, False, (MenuParameter(0, 'Zurück', True), MenuParameter(1, 'Reset/Bus Scan HCP2 Bus', False), MenuParameter(2, 'Reset Parameter ab 20 - 36', False), MenuParameter(3, 'Werksreset', False))),
    MenuSetting(38, 29, 'Erweiterte Menüs freigeschaltet', None, False, (MenuParameter(0, 'Platzhalter', True),)),
    MenuSetting(39, 30, 'Impulsverhalten', None, False, (MenuParameter(0, 'Impuls verlängert die Aufhaltezeit (mit allen Befehlsgeräten außer Tor Zu)', True), MenuParameter(1, 'Impuls bricht die Aufhaltezeit ab ( mit allen Befehlsgeräten außer Tor Auf)', False))),
    MenuSetting(40, 31, 'Betriebsart', None, False, (MenuParameter(1, 'Impulsfolge', True), MenuParameter(2, 'Impulsfolge nur in der Endlage', False), MenuParameter(3, 'sofortige Richtungsumkehr bei Richtungsbefehl', False))),
    MenuSetting(41, 32, 'Sicherheitseinrichtung SE1', None, False, (MenuParameter(0, 'deaktiviert', True), MenuParameter(1, '2-Draht LS statisch / dynamisch', False))),
    MenuSetting(42, 33, 'Sicherheitseinrichtung SE1 Funktion', None, False, (MenuParameter(0, 'Wirkrichtung Tor-Zu kurzes Reversieren', False), MenuParameter(1, 'Wirkrichtung Tor-Zu langes Reversieren', True), MenuParameter(2, 'Wirkrichtung Tor-Zu entlasten', False), MenuParameter(3, 'Wirkrichtung Tor-Auf kurzes Reversieren', False), MenuParameter(4, 'Wirkrichtung Tor-Auf langes Reversieren', False), MenuParameter(5, 'Wirkrichtung Tor-Auf entlasten', False), MenuParameter(6, 'Wirkrichtung Tor-Zu und Tor-Auf kurzes Reversieren', False))),
    MenuSetting(43, 34, 'Sicherheitseinrichtung SE2', None, False, (MenuParameter(0, 'deaktiviert', True), MenuParameter(1, 'SKS', False), MenuParameter(2, 'VL', False), MenuParameter(3, 'Funk-SKS', False), MenuParameter(4, '8k2', False))),
    MenuSetting(44, 35, 'Sicherheitseinrichtung SE2 Funktion', None, False, (MenuParameter(0, 'Wirkrichtung Tor-Zu kurzes Reversieren', False), MenuParameter(1, 'Wirkrichtung Tor-Zu langes Reversieren', True), MenuParameter(2, 'Wirkrichtung Tor-Zu entlasten', False), MenuParameter(3, 'Wirkrichtung Tor-Auf kurzes Reversieren', False), MenuParameter(4, 'Wirkrichtung Tor-Auf langes Reversieren', False), MenuParameter(5, 'Wirkrichtung Tor-Auf entlasten', False), MenuParameter(6, 'Wirkrichtung Tor-Zu und Tor-Auf kurzes Reversieren', False))),
    MenuSetting(48, 36, 'Verhalten bei Ansprechen der Kraftbegrenzung in Wirkrichtung Auf', None, False, (MenuParameter(0, 'Entlasten', True), MenuParameter(1, 'Kurzes Reversieren', False), MenuParameter(2, 'Langes Reversieren', False))),
    MenuSetting(49, 37, 'Verhalten bei Ansprechen der Kraftbegrenzung in Wirkrichtung Zu', None, False, (MenuParameter(0, 'Entlasten', False), MenuParameter(1, 'Kurzes Reversieren', True), MenuParameter(2, 'Langes Reversieren', False))),
    MenuSetting(50, 38, 'Kraftbegrenzung Tor-Auf', None, False, (MenuParameter(0, 'Stufe 0', False), MenuParameter(1, 'Stufe 1', False), MenuParameter(2, 'Stufe 2', False), MenuParameter(3, 'Stufe 3', False), MenuParameter(4, 'Stufe 4', True), MenuParameter(5, 'Stufe 5', False), MenuParameter(6, 'Stufe 6', False), MenuParameter(7, 'Stufe 7', False), MenuParameter(8, 'Stufe 8', False), MenuParameter(9, 'Stufe 9', False), MenuParameter(10, 'Stufe 10', False))),
    MenuSetting(51, 39, 'Kraftbegrenzung Tor-Zu', None, False, (MenuParameter(0, 'Stufe 0', False), MenuParameter(1, 'Stufe 1', False), MenuParameter(2, 'Stufe 2', False), MenuParameter(3, 'Stufe 3', False), MenuParameter(4, 'Stufe 4', True), MenuParameter(5, 'Stufe 5', False), MenuParameter(6, 'Stufe 6', False), MenuParameter(7, 'Stufe 7', False), MenuParameter(8, 'Stufe 8', False), MenuParameter(9, 'Stufe 9', False), MenuParameter(10, 'Stufe 10', False))),
    MenuSetting(52, 40, 'Geschwindigkeit Tor-Auf', None, False, (MenuParameter(0, 'Sehr schnell', True), MenuParameter(1, 'Schnell', False), MenuParameter(2, 'Mittel', False), MenuParameter(3, 'Langsam', False))),
    MenuSetting(53, 41, 'Geschwindigkeit Tor-Zu', None, False, (MenuParameter(0, 'Sehr schnell', False), MenuParameter(1, 'Schnell', False), MenuParameter(2, 'Mittel', False), MenuParameter(3, 'Langsam', True))),
    MenuSetting(54, 42, 'Schleichfahrtgeschwindigkeit Tor-Auf', None, False, (MenuParameter(0, 'Maximal', False), MenuParameter(1, 'Mittel', True), MenuParameter(2, 'Langsam', False))),
    MenuSetting(55, 43, 'Schleichfahrtgeschwindigkeit Tor-Zu', None, False, (MenuParameter(0, 'Maximal', False), MenuParameter(1, 'Mittel', True), MenuParameter(2, 'Langsam', False))),
    MenuSetting(56, 44, 'Startpunkte Schleichfahrt Tor-Auf', None, False, (MenuParameter(0, 'Kurz', False), MenuParameter(1, 'Mittel', True), MenuParameter(2, 'Lang', False))),
    MenuSetting(57, 45, 'Startpunkte Schleichfahrt Tor-Zu', None, False, (MenuParameter(0, 'Kurz', False), MenuParameter(1, 'Mittel', True), MenuParameter(2, 'Lang', False))),
    MenuSetting(58, 46, 'Sondertortyp', None, False, (MenuParameter(0, 'Nicht gesetzt', True), MenuParameter(1, 'Gesetzt', False))),
    MenuSetting(59, 47, 'Gurtentlastung Tor-Auf', None, False, (MenuParameter(0, 'Ohne', False), MenuParameter(1, 'Kurz', False), MenuParameter(2, 'Mittel', True), MenuParameter(3, 'Lang', False))),
    MenuSetting(61, 48, 'Position ändern', None, False, (MenuParameter(0, 'Position Lüften default', True), MenuParameter(1, 'Position ändern', False))),
    MenuSetting(62, 49, 'Softstartrampe', None, False, (MenuParameter(0, 'Position Softstartrampe default', True), MenuParameter(1, 'Position ändern', False))),
    MenuSetting(66, 50, 'Max. Lernkräfte', None, False, (MenuParameter(0, 'Stufe 0', True), MenuParameter(1, 'Stufe 1', False), MenuParameter(2, 'Stufe 2', False))),
    MenuSetting(88, 51, 'Anzeige Antriebstyp und Ausführung (Menu 1-9)', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(89, 52, 'Wartungsanzeige', None, False, (MenuParameter(0, 'deaktiviert', True), MenuParameter(1, '1.000', False), MenuParameter(2, '2.000', False), MenuParameter(3, '3.000', False), MenuParameter(4, '4.000', False), MenuParameter(5, '5.000', False), MenuParameter(6, '7.500', False), MenuParameter(7, '10.000', False), MenuParameter(8, '180 Tage', False), MenuParameter(9, '360 Tage', False))),
    MenuSetting(90, 53, 'Zähler Wartungsanzeige zurück setzen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(91, 54, 'Letzte 10 Fehlermeldungen auslesen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(92, 55, 'Position letzter Kraftfehler anfahren', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(93, 56, 'Fehlerspeicher zurücksetzen/löschen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(94, 57, 'Torzyklen unvollständig auslesen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(95, 58, 'Betriebsstunden gesamt auslesen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(96, 59, 'Reversiergrenzen zurücksetzen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(97, 60, 'Betriebskräfte zurücksetzen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(98, 61, 'Einstellungen Schleichfahrten zurücksetzen', None, True, (MenuParameter(-1, 'Folgeablauf', True),)),
    MenuSetting(99, 62, 'Reset', None, True, (MenuParameter(0, 'Zurück', True), MenuParameter(1, 'Reset/Bus Scan HCP2 Bus', False), MenuParameter(2, 'Reset Parameter ab 20-36', False), MenuParameter(3, 'Reset Parameter ab 38-96 (90-95 nicht)', False), MenuParameter(4, 'Werksreset', False))),
    MenuSetting(101, 101, 'Antenne', None, False, (MenuParameter(0, 'Interne Antenne', True), MenuParameter(1, 'Externe Antenne', False))),
)


DRIVE_MENU_TABLES: Tuple[DriveMenuTable, ...] = (
    DriveMenuTable(1, 1, "HET", ("EE001813-00.aa", "EE001851-00.aa"), _HET_1_1_SETTINGS),
    DriveMenuTable(1, 2, "HET", ("EE001851-00.ac", "EE001813-01.aa"), _HET_1_2_SETTINGS),
    DriveMenuTable(2, 1, "Supramatic Serie 4", ("EE001932-01.ae", "EE002262-00.aa"), _SM4_PRODUCT_ID_1_SETTINGS),
    DriveMenuTable(2, 2, "Supramatic Serie 4", ("EE001932-02.ai", "EE002545-00.aa", "EE002547-00.aa", "EE002535-00.aa", "EE002262-02.af", "EE002397-00.aa"), _SM4_PRODUCT_ID_2_SETTINGS),
    DriveMenuTable(2, 17, "Rollmatic 2", ("EE001822-01.ad",), _ROLLMATIC_2_SETTINGS),
    DriveMenuTable(2, 33, "SilentDrive 2", ("EE002449-00.aa",), _SILENTDRIVE_2_AA_SETTINGS),
    DriveMenuTable(2, 33, "SilentDrive 2", ("EE002449-00.ai",), _SILENTDRIVE_2_AI_SETTINGS),
    DriveMenuTable(2, 49, "Supramatic 4 H4", ("EE003068-00.aa", "EE003070-00.aa"), _SUPRAMATIC_4_H4_SETTINGS),
)

# Backward-compat aliases - our one live-tested device (F1:26:AF:CC:41:86).
SUPRAMATIC_E4_MENU_TABLE: Tuple[MenuSetting, ...] = _SM4_PRODUCT_ID_2_SETTINGS


def menu_tables_for_product(product_class: int, product_id: int) -> Tuple[DriveMenuTable, ...]:
    """All known DriveMenuTable entries for a (product_class, product_id) pair - usually
    one, but e.g. SilentDrive 2 (2, 33) has two (genuine firmware-revision variants)."""
    return tuple(t for t in DRIVE_MENU_TABLES
                 if t.product_class == product_class and t.product_id == product_id)


def menu_table_for_product(product_class: int, product_id: int,
                            software_number: Optional[str] = None) -> Optional[DriveMenuTable]:
    """Picks the DriveMenuTable for a (product_class, product_id) pair, disambiguating
    via `software_number` (an "EE......-NN.xx" string, e.g. from GET_SOFTWARE_VERSION)
    if there is more than one candidate. Returns None if the product is unknown, or if
    it's ambiguous and no (matching) software_number was given."""
    candidates = menu_tables_for_product(product_class, product_id)
    if len(candidates) == 1:
        return candidates[0]
    if software_number:
        for table in candidates:
            if software_number in table.software_numbers:
                return table
    return None


def menu_setting_for_number(settings: Sequence[MenuSetting], menu_number: int) -> Optional[MenuSetting]:
    """Looks up a MenuSetting by its human-facing menu number (e.g. 25) within a given
    product's settings table (DriveMenuTable.settings, or SUPRAMATIC_E4_MENU_TABLE)."""
    return next((m for m in settings if m.menu_number == menu_number), None)


def menu_setting_for_wire_group(settings: Sequence[MenuSetting], menu_group: int) -> Optional[MenuSetting]:
    """Looks up a MenuSetting by its wire byte (the `menu_group` used in
    GET_PROPERTIES/SET_PROPERTIES payloads and PROPERTIES_LIST notifications)."""
    return next((m for m in settings if m.menu_group == menu_group), None)


def wire_group_for_menu_number(settings: Sequence[MenuSetting], menu_number: int) -> Optional[int]:
    """Convenience shortcut: human menu number -> wire byte, or None if unknown."""
    setting = menu_setting_for_number(settings, menu_number)
    return setting.menu_group if setting is not None else None
