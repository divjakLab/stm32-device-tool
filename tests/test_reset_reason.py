from devicetool.core.reset_reason import (decode_reset_flags, describe_reset,
                                          parse_firmware_reset_line)


def test_cleared_flags_real_value():
    assert decode_reset_flags(0x00004400) == []
    assert describe_reset(0x00004400) == "Unknown (reset flags already cleared by the firmware)"


def test_single_flags():
    assert describe_reset(1 << 26) == "Reset pin (button or debugger)"
    assert describe_reset(1 << 29) == "Independent watchdog"
    assert describe_reset(1 << 30) == "Window watchdog"
    assert describe_reset(1 << 31) == "Low-power mode reset"
    assert describe_reset(1 << 25) == "Option-byte load"


def test_pin_flag_hidden_when_another_reason_exists():
    assert describe_reset((1 << 27) | (1 << 26)) == "Power-on / brown-out"
    assert describe_reset((1 << 28) | (1 << 26)) == "Software reset"
    assert describe_reset((1 << 29) | (1 << 28) | (1 << 26)) == "Independent watchdog, Software reset"


def test_parse_firmware_line():
    line = "##### Reset cause: PIN  (RCC->CSR = 0x0C004400)"
    assert parse_firmware_reset_line(line) == 0x0C004400
    assert parse_firmware_reset_line("Reset cause: (RCC->CSR = 0x4400)") == 0x4400
    assert parse_firmware_reset_line("BLE advertising is started") is None
