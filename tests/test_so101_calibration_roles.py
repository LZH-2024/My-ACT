"""离线校验角色隔离及旧命令兼容性；所有串口和校准总线均被替身拦截。"""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from my_act.hardware.so101.calibration import (
    HOMING_DIAGRAMS, MOTORS, REGISTERS, WRITABLE, half_turn_offsets,
    resolve_calibration_paths, validate_calibration,
)

PROJECT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, PROJECT / "robots/so101/scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


calibrate = load_script("calibrate")
check = load_script("check_connection")


class RoleTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.temp = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.root = self.temp / "robots/so101/calibration"
        for module in (calibrate, check):
            self.stack.enter_context(patch.object(
                module, "__file__", str(self.temp / "robots/so101/scripts" / f"{module.__name__}.py")))
        # 即使某项替身漏配，也禁止任何测试打开真实串口。
        self.stack.enter_context(patch("serial.Serial", side_effect=AssertionError("禁止访问真实串口")))

    def fixture(self, role="leader", name="leader01", nested=False):
        device, path = resolve_calibration_paths(self.root, role, name)
        if nested:
            path = device / "session/calibration.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        calibration = {n: dict(id=i, drive_mode=0, homing_offset=12,
                               range_min=1000, range_max=3000) for n, i in MOTORS.items()}
        calibration["wrist_roll"].update(range_min=0, range_max=4095)
        path.write_text(json.dumps(calibration))
        backup = device / "backups/session/registers_before.json"
        backup.parent.mkdir(parents=True, exist_ok=True)
        value = dict(role=role, device_name=name, port="/dev/mock", baudrate=1000000,
                     motor_ids=MOTORS, created_at="offline",
                     registers_address_length=REGISTERS,
                     raw_values={n: {"Phase": 19, "Lock": 1} for n in MOTORS})
        backup.write_text(json.dumps(value))
        return path, backup, calibration

    def test_role_defaults_and_nested_path(self):
        for role in ("leader", "follower"):
            with self.subTest(role=role):
                device, path = resolve_calibration_paths(self.root, role, "arm01")
                self.assertEqual(path, self.root / role / "arm01/calibration.json")
                self.assertEqual(resolve_calibration_paths(
                    self.root, role, None, device / "session/calibration.json")[0], device)

    def test_wrong_role_device_and_invalid_paths(self):
        for role, name, path in [
            ("follower", "follower01", self.root / "leader/leader01/calibration.json"),
            ("leader", "leader01", self.root / "follower/follower01/calibration.json"),
            ("follower", "follower01", self.root / "follower/other/calibration.json"),
            ("follower", "follower01", self.root / "follower/follower01/../../leader/a.json"),
            ("follower", "../leader", None),
            ("other", "arm01", None),
            ("follower", "follower01", self.root / "follower/follower01/file.txt"),
        ]:
            with self.subTest(role=role, name=name, path=path), self.assertRaises(ValueError):
                resolve_calibration_paths(self.root, role, name, path)

    def test_symlinks_cannot_cross_device_boundary(self):
        leader, _, _ = self.fixture()
        follower = self.root / "follower/follower01"
        follower.parent.mkdir()
        follower.symlink_to(leader.parent, target_is_directory=True)
        with self.assertRaises(ValueError):
            resolve_calibration_paths(self.root, "follower", "follower01")
        follower.unlink()
        follower.mkdir()
        (follower / "calibration.json").symlink_to(leader)
        with self.assertRaises(ValueError):
            resolve_calibration_paths(self.root, "follower", "follower01")

    def test_readonly_old_leader_command_and_follower_metadata(self):
        for role, name in (("leader", "leader01"), ("follower", "follower01")):
            path, backup, expected = self.fixture(role, name, nested=True)
            with contextlib.redirect_stdout(io.StringIO()):
                kwargs = {} if role == "leader" else dict(role=role, device_name=name)
                actual, _ = check.load_comparison(path, backup, "/dev/mock", 1000000, **kwargs)
            self.assertEqual(actual, expected)

    def test_readonly_rejects_mismatched_backup_identity(self):
        path, backup, _ = self.fixture("follower", "follower01")
        original = json.loads(backup.read_text())
        for key, wrong in (("role", "leader"), ("device_name", "leader01"),
                           ("port", "/dev/other"), ("baudrate", 115200)):
            backup.write_text(json.dumps({**original, key: wrong}))
            with self.subTest(key=key), self.assertRaises(ValueError):
                check.load_comparison(path, backup, "/dev/mock", 1000000, "follower", "follower01")

    def test_readonly_rejects_other_role_backup_and_default_leader(self):
        leader, leader_backup, _ = self.fixture()
        follower, follower_backup, _ = self.fixture("follower", "follower01")
        with self.assertRaises(ValueError):
            check.load_comparison(follower, leader_backup, "/dev/mock", 1000000, "follower", "follower01")
        with self.assertRaises(ValueError):
            check.load_comparison(follower, follower_backup, "/dev/mock", 1000000)
        # 不读取错误角色的文件。
        with patch.object(Path, "read_text", side_effect=AssertionError("不能读取错误角色文件")):
            with self.assertRaises(ValueError):
                check.load_comparison(leader, leader_backup, "/dev/mock", 1000000, "follower", "follower01")

    def test_invalid_cli_fails_before_constructing_bus(self):
        for module, port_class, extra in (
            (calibrate, "CalibrationBus", []),
            (check, "ReadOnlyCheckPort", ["--register-backup", "/tmp/not-used.json"]),
        ):
            args = ["tool", "--role", "follower", "--device-name", "follower01",
                    "--port", "/dev/mock", "--calibration-file",
                    str(self.root / "leader/leader01/calibration.json"), *extra]
            with self.subTest(module=module.__name__), patch("sys.argv", args), \
                    patch.object(module, port_class) as bus, \
                    contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                module.main()
            self.assertEqual(error.exception.code, 2)
            bus.assert_not_called()


    def test_readonly_cli_keeps_legacy_defaults_and_accepts_follower(self):
        class StopBeforeSerial(Exception):
            pass

        follower, backup, _ = self.fixture("follower", "follower01")
        commands = [
            (["tool", "--port", "/dev/mock"], "leader"),
            (["tool", "--role", "follower", "--port", "/dev/mock",
              "--device-name", "follower01", "--calibration-file", str(follower),
              "--register-backup", str(backup)], "follower"),
        ]
        for args, role in commands:
            output = io.StringIO()
            with self.subTest(role=role), patch("sys.argv", args), \
                    patch.object(check, "ReadOnlyCheckPort", side_effect=StopBeforeSerial) as port, \
                    contextlib.redirect_stdout(output), self.assertRaises(StopBeforeSerial):
                check.main()
            port.assert_called_once_with("/dev/mock")
            self.assertIn(f"角色={role}", output.getvalue())

    def test_symlinked_backup_is_rejected_before_file_read(self):
        _, leader_backup, _ = self.fixture()
        follower, backup, _ = self.fixture("follower", "follower01")
        backup.unlink()
        backup.symlink_to(leader_backup)
        with patch.object(Path, "read_text", side_effect=AssertionError("不能读取跨角色备份")):
            with self.assertRaises(ValueError):
                check.load_comparison(follower, backup, "/dev/mock", 1000000, "follower", "follower01")

    def test_new_follower_calibration_isolated_from_leader(self):
        leader, leader_backup, _ = self.fixture()
        originals = {p: p.read_bytes() for p in (leader, leader_backup)}
        device, target = resolve_calibration_paths(self.root, "follower", "follower01")
        events = []

        class FakeBus:
            def __init__(self, port, baudrate):
                self.values = {n: dict(Torque_Enable=1, Lock=1, Operating_Mode=0,
                                      Phase=19, Homing_Offset=12,
                                      Min_Position_Limit=0, Max_Position_Limit=4095) for n in MOTORS}

            def open(self):
                events.append("open")

            def close(self):
                events.append("close")

            def read_raw(self, name, register):
                if register == "ID":
                    return MOTORS[name]
                if register == "Model_Number":
                    return 777
                return self.values[name][register]

            read = read_raw

            def write(self, name, register, value):
                # 所有写入只修改替身内存，同时检查首次写入前已备份正确角色。
                backups = list(device.glob("backups/*/registers_before.json"))
                assert len(backups) == 1
                assert json.loads(backups[0].read_text())["role"] == "follower"
                assert register in WRITABLE
                assert register != "Torque_Enable" or value == 0
                events.append((name, register, value))
                self.values[name][register] = value

            def positions(self):
                return {n: 2100 - self.values[n]["Homing_Offset"] for n in MOTORS}

        mins = {n: 1000 for n in MOTORS}
        maxes = {n: 3000 for n in MOTORS}
        mins["wrist_roll"], maxes["wrist_roll"] = 0, 4095
        output = io.StringIO()
        args = ["tool", "--role", "follower", "--port", "/dev/mock", "--device-name", "follower01"]
        with patch("sys.argv", args), patch("sys.stdin.isatty", return_value=True), \
                patch("builtins.input", side_effect=["DISABLE", "WRITE", "", "WRITE", "SAVE"]), \
                patch.object(calibrate, "CalibrationBus", FakeBus), \
                patch.object(calibrate, "collect_ranges", return_value=(mins, maxes)), \
                contextlib.redirect_stdout(output):
            calibrate.main()
        validate_calibration(json.loads(target.read_text()))
        for path, data in originals.items():
            self.assertEqual(path.read_bytes(), data)
        self.assertIn("从臂参考姿态", output.getvalue())
        self.assertIn("托住或妥善放置从臂", output.getvalue())
        self.assertNotIn("← handle", output.getvalue())
        self.assertEqual(events[-1], "close")

    def test_legacy_leader_cli_and_cancel_before_bus(self):
        path, _, _ = self.fixture()
        args = ["tool", "--port", "/dev/mock", "--device-name", "leader01",
                "--calibration-file", str(path)]
        output = io.StringIO()
        with patch("sys.argv", args), patch("sys.stdin.isatty", return_value=True), \
                patch("builtins.input", return_value="cancel"), \
                patch.object(calibrate, "CalibrationBus") as bus, \
                contextlib.redirect_stdout(output), self.assertRaises(RuntimeError):
            calibrate.main()
        bus.assert_not_called()
        self.assertIn("角色=leader", output.getvalue())

    def test_offsets_and_role_reference_are_compatible(self):
        offsets = half_turn_offsets({n: 2100 for n in MOTORS})
        self.assertEqual(set(offsets.values()), {53})
        self.assertIn("← handle", HOMING_DIAGRAMS["leader"])
        self.assertIn("← fixed claw", HOMING_DIAGRAMS["follower"])
        self.assertNotIn("← handle", HOMING_DIAGRAMS["follower"])


if __name__ == "__main__":
    unittest.main()
