"""Shared pytest options."""


def pytest_addoption(parser):
    parser.addoption(
        "--regen-goldens", action="store_true", default=False,
        help="rewrite facegen golden files (do this deliberately on a "
             "hotwell revision that moves a setpoint)")
