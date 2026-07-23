import re

SERIAL_RE = re.compile(r"^[A-Za-z0-9]*$")


def gs1_check_digit(data: str) -> int:
    """Calculate the GS1 Mod-10 check digit."""
    total = 0
    for i, digit in enumerate(reversed(data)):
        n = int(digit)
        total += n * 3 if i % 2 == 0 else n
    return (10 - (total % 10)) % 10


def validate_grai(barcode: str) -> None:
    """
    Validate a GRAI barcode.

    Raises:
        ValueError: if the barcode is not a valid GRAI.
    """

    MIN_LENGTH = 18  # AI (8003) + filler (0) + 13-digit asset identifier

    if len(barcode) < MIN_LENGTH:
        raise ValueError(
            f"The barcode is too short. Expected at least {MIN_LENGTH} characters."
        )

    if not barcode.startswith("80030"):
        raise ValueError("The barcode does not start with 80030.")

    asset_identifier = barcode[5:18]
    serial = barcode[18:]

    if not asset_identifier.isdigit():
        raise ValueError("The asset identifier must consist of exactly 13 digits.")

    if len(serial) > 16:
        raise ValueError("The serial number may not exceed 16 characters.")

    if not SERIAL_RE.fullmatch(serial):
        raise ValueError("The serial number may contain only letters and digits.")

    # expected = gs1_check_digit(asset_identifier[:-1])
    # actual = int(asset_identifier[-1])

    # if expected != actual:
    #     raise ValueError(
    #         f"Invalid GS1 check digit. Expected {expected}, found {actual}."
    #     )
